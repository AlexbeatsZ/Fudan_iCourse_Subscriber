from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import replay_library as lib
from src.data.database import Database
from scripts.merge_db import merge
from src.data.sharder import shard_database, load_index, reassemble_database


class LibraryTests(unittest.TestCase):
    def test_number_and_subtitle_timing(self):
        self.assertEqual(lib.lesson_stem(1), "第01节")
        self.assertEqual(lib.lesson_stem(11), "第11节")
        text = lib.subtitle_text([{"start_ms": 4574123, "end_ms": 4578000, "text": "A < B"}])
        self.assertIn("01:16:14.123 --> 01:16:18.000", text)
        self.assertIn("A &lt; B", text)
        with self.assertRaises(ValueError):
            lib.subtitle_text([{"start_ms": -1, "end_ms": 100, "text": "invalid"}])

    def test_transfer_keeps_source_on_conflict_and_handles_offline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = {"destination": str(root/"network"), "fallback": str(root/"downloads")}
            src = lib.course_folder(root/"downloads", "Course", "1")
            stem = lib.lesson_stem(1)
            (src/(stem+".mp4")).write_bytes(b"video content")
            lib.write_json(src/(stem+".mp4.json"), {"complete": True, "total": 13})
            lib.write_json(src/(stem+".lesson.json"), {"sub_id": "2", "course_id": "1"})
            with patch.object(lib, "writable", return_value=False):
                self.assertEqual(lib.transfer(cfg), 0)
            self.assertTrue((src/(stem+".mp4")).exists())
            dst = lib.course_folder(root/"network", "Course", "1")
            (dst/(stem+".mp4")).write_bytes(b"different")
            with self.assertRaises(FileExistsError):
                lib.transfer(cfg)
            self.assertTrue((src/(stem+".mp4")).exists())
            (dst/(stem+".mp4")).unlink()
            self.assertEqual(lib.transfer(cfg), 1)
            self.assertFalse(src.exists())
            self.assertFalse((root/"downloads").exists())
            self.assertEqual((dst/(stem+".mp4")).read_bytes(), b"video content")

    def test_transfer_accepts_existing_same_size_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = {"destination": str(root/"network"), "fallback": str(root/"downloads")}
            src = lib.course_folder(root/"downloads", "Course", "1")
            dst = lib.course_folder(root/"network", "Course", "1")
            stem = lib.lesson_stem(1)
            (src/(stem+".mp4")).write_bytes(b"source")
            lib.write_json(src/(stem+".mp4.json"), {"complete": True, "total": 6})
            (dst/(stem+".mp4")).write_bytes(b"target")
            lib.write_json(dst/(stem+".mp4.json"), {"complete": True, "total": 6,
                                                     "validator": "older record text"})
            (dst/(stem+".mp4.transfer")).write_bytes(b"stale")
            (dst/(stem+".mp4.json.transfer")).write_bytes(b"stale")

            self.assertEqual(lib.transfer(cfg), 1)
            self.assertFalse(src.exists())
            self.assertEqual((dst/(stem+".mp4")).read_bytes(), b"target")
            self.assertFalse((dst/(stem+".mp4.transfer")).exists())
            self.assertFalse((dst/(stem+".mp4.json.transfer")).exists())

    def test_transfer_clears_incomplete_staging_but_preserves_complete_video_offline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = {"destination": str(root/"network"), "fallback": str(root/"downloads")}
            old = lib.course_folder(root/"downloads", "Old", "1")
            pending = lib.course_folder(root/"downloads", "Pending", "2")
            (pending/"第01节.mp4.part").write_bytes(b"partial")
            lib.write_json(pending/"第01节.mp4.json", {"complete": False, "total": 9})
            lib.write_json(pending/"第01节.lesson.json", {"course_id": "2", "sub_id": "3"})
            (pending/"第01节.vtt").write_text("WEBVTT\n")
            assets = pending/"第01节.assets"
            assets.mkdir()
            (assets/"00001.jpg.part").write_bytes(b"partial slide")
            complete = lib.course_folder(root/"downloads", "Complete", "3")
            (complete/"第01节.mp4").write_bytes(b"complete")
            lib.write_json(complete/"第01节.mp4.json", {"complete": True, "total": 8})

            with patch.object(lib, "writable", return_value=False):
                self.assertEqual(lib.transfer(cfg), 0)
            self.assertFalse(old.exists())
            self.assertFalse(pending.exists())
            self.assertTrue((complete/"第01节.mp4").exists())

            self.assertEqual(lib.transfer(cfg), 1)
            self.assertFalse((root/"downloads").exists())
            self.assertEqual((root/"network"/"Complete"/"第01节.mp4").read_bytes(), b"complete")

    def test_failed_copy_removes_transfer_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root/"video.mp4"
            source.write_bytes(b"complete")
            target = root/"network"/"video.mp4"
            with patch.object(lib.shutil, "copyfileobj", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    lib.copy_size_checked(source, target)
            self.assertTrue(source.exists())
            self.assertFalse(target.exists())
            self.assertFalse(target.with_name("video.mp4.transfer").exists())

    def test_rog_failed_download_discards_partial_but_keeps_complete_video(self):
        from desktop.downloader import discard_partial_video
        with tempfile.TemporaryDirectory() as td:
            video = Path(td)/"第01节.mp4"
            part = video.with_suffix(".mp4.part")
            record = video.with_suffix(".mp4.json")
            part.write_bytes(b"partial")
            lib.write_json(record, {"complete": False, "total": 100})
            discard_partial_video(video)
            self.assertFalse(part.exists())
            self.assertFalse(record.exists())

            video.write_bytes(b"complete")
            part.write_bytes(b"stale")
            lib.write_json(record, {"complete": True, "total": 8})
            discard_partial_video(video)
            self.assertEqual(video.read_bytes(), b"complete")
            self.assertTrue(record.exists())
            self.assertFalse(part.exists())

    def test_transcript_survives_db_merge_and_encrypted_shards(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = Database(str(root/"local.db"))
            db.upsert_course("1", "Course", "Teacher")
            db.insert_lecture("2", "1", "Lesson", "2026-09-19")
            segments = [{"start_ms": 0, "end_ms": 1200, "text": "hello"}]
            db.update_transcript("2", "hello", segments)
            db.conn.close()
            remote = root/"remote.db"
            merge(str(root/"local.db"), str(remote))
            out = root/"shards"; out.mkdir()
            shard_database(str(remote), str(out), "test-password")
            index = load_index(str(out/"icourse-index.enc"), "test-password")
            result = root/"result.db"
            reassemble_database(index, str(out/"shards"), str(result), "test-password")
            with closing(sqlite3.connect(result)) as conn:
                value = conn.execute("SELECT transcript_segments FROM lectures WHERE sub_id='2'").fetchone()[0]
            self.assertEqual(json.loads(value), segments)

    def test_app_media_ranges_and_request_token(self):
        from desktop.server import make_app
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"Course").mkdir()
            (root/"Course"/"第01节.mp4").write_bytes(b"0123456789")
            cfg = {"destination": str(root), "fallback": str(root/"fallback"), "courses": []}
            with patch("desktop.server.settings", return_value=cfg):
                server = make_app(0)
                worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    from urllib.parse import quote
                    req = Request(base+"/media/0/Course/"+quote("第01节.mp4"), headers={"Range": "bytes=4-7"})
                    with urlopen(req) as response:
                        self.assertEqual(response.status, 206)
                        self.assertEqual(response.read(), b"4567")
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(Request(base+"/api/run", data=b'{"command":"download"}', method="POST"))
                    self.assertEqual(denied.exception.code, 403)
                finally:
                    server.shutdown(); server.server_close(); worker.join()


if __name__ == "__main__":
    unittest.main()
