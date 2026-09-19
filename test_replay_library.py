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
            self.assertFalse((src/(stem+".mp4")).exists())
            self.assertEqual((dst/(stem+".mp4")).read_bytes(), b"video content")

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
