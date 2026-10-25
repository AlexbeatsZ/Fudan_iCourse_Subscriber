from contextlib import closing, ExitStack, redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock, call, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile

import replay_library as lib
from desktop import downloader
from src.data import crypto_box
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


class CloudLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root/"personal"
        self.cache = self.root/"friend"/"cloud.db"
        self.version = self.cache.with_name("cloud.db.version.json")
        self.password_file = self.root/"password.txt"
        self.secret = " fixture 密码 "
        self.password_file.write_text(self.secret + "\n", encoding="utf-8-sig")
        self.key = crypto_box.derive_custom_password(self.secret)
        self.config = {"repository": "friend/repo", "database": str(self.cache),
                       "password_file": str(self.password_file)}
        source = self.root/"source.db"
        database = Database(str(source))
        database.upsert_course("1", "Fixture course", "Teacher")
        database.conn.close()
        self.plaintext = source.read_bytes()
        self.enterContext(patch.object(lib, "RUNTIME", self.runtime))
        self.enterContext(patch.object(downloader, "RUNTIME", self.runtime))
        self.credentials = self.enterContext(patch.object(
            downloader, "credentials", side_effect=AssertionError("Personal credentials used")))
        self.enterContext(patch.dict(os.environ, {
            "DB_PASSWORD": "environment-password", "DB_PASSWORD_PREVIOUS": "previous-password",
            "DASHSCOPE_API_KEY": "fixture-api", "SMTP_PASSWORD": "fixture-smtp",
            "FUDAN_STUID": "fixture-student", "FUDAN_UISPSW": "fixture-uis",
            "GITHUB_TOKEN": "",
        }))

    def responses(self, files=None, sha="commit", key=None):
        if files is None:
            files = {"icourse.db.enc": crypto_box.encrypt(
                self.plaintext, self.key if key is None else key)}
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, content in files.items():
                archive.writestr("fixture/data/" + name, content)
        return [Mock(json=lambda: {"object": {"sha": sha}}), Mock(content=output.getvalue())]

    def seed_cache(self):
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_bytes(self.plaintext)
        self.version.write_text('{"sha":"old","key_id":"old"}', encoding="utf-8")
        return self.cache.read_bytes(), self.version.read_bytes()

    def test_password_file_derives_custom_key_with_utf8_and_bom(self):
        for encoding in ("utf-8", "utf-8-sig"):
            with self.subTest(encoding=encoding):
                self.password_file.write_bytes((self.secret + "\r\n").encode(encoding))
                with (patch("requests.get", side_effect=self.responses(sha=encoding)),
                      patch.object(crypto_box, "password_candidates",
                                   wraps=crypto_box.password_candidates) as candidates):
                    self.assertEqual(downloader.cloud_database(self.config), self.cache)
                self.assertEqual(candidates.call_args_list, [
                    call(db_password=self.secret),
                    call(db_password=self.secret, include_legacy=True),
                ])
                self.assertEqual(self.cache.read_bytes(), self.plaintext)
                self.assertFalse(self.config["_needs_rekey"])
                version = lib.read_json(self.version)
                self.assertEqual(version["repository"], "friend/repo")
                self.assertNotIn(self.secret, self.version.read_text())
                self.assertNotIn(self.key, self.version.read_text())
        self.credentials.assert_not_called()
        self.assertFalse(self.runtime.exists())

    def test_password_file_decrypts_existing_sharded_format(self):
        output = self.root/"sharded"
        output.mkdir()
        shard_database(str(self.root/"source.db"), str(output), self.key)
        files = {path.relative_to(output).as_posix(): path.read_bytes()
                 for path in output.rglob("*.enc")}
        with patch("requests.get", side_effect=self.responses(files)):
            result = downloader.cloud_database(self.config)
        with closing(sqlite3.connect(result)) as database:
            self.assertEqual(database.execute("SELECT count(*) FROM courses").fetchone()[0], 1)
        self.assertFalse(self.config["_needs_rekey"])
        self.credentials.assert_not_called()

    def test_cache_requires_repository_sha_and_key_identity(self):
        with patch("requests.get", side_effect=self.responses()):
            downloader.cloud_database(self.config)
        reference = Mock(json=lambda: {"object": {"sha": "commit"}})
        with patch("requests.get", side_effect=[reference]) as get:
            downloader.cloud_database(self.config)
        self.assertEqual(get.call_count, 1)
        self.config["repository"] = "other/repo"
        with patch("requests.get", side_effect=self.responses()) as get:
            downloader.cloud_database(self.config)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(lib.read_json(self.version)["repository"], "other/repo")
        with patch("requests.get", side_effect=self.responses(sha="next")) as get:
            downloader.cloud_database(self.config)
        self.assertEqual(get.call_count, 2)
        old_key_id = lib.read_json(self.version)["key_id"]
        self.password_file.write_text("rotated-password", encoding="utf-8")
        rotated_key = crypto_box.derive_custom_password("rotated-password")
        with patch("requests.get", side_effect=self.responses(sha="next", key=rotated_key)) as get:
            downloader.cloud_database(self.config)
        self.assertEqual(get.call_count, 2)
        self.assertNotEqual(lib.read_json(self.version)["key_id"], old_key_id)

    def test_failure_preserves_database_and_version_without_environment_fallback(self):
        previous = self.seed_cache()
        failures = {
            "network": OSError("fixture network failure"),
            "archive": [Mock(json=lambda: {"object": {"sha": "commit"}}),
                        Mock(content=b"not a zip")],
            "password": self.responses(key=crypto_box.derive_custom_password("environment-password")),
            "integrity": self.responses({"icourse.db.enc": crypto_box.encrypt(
                b"SQLite format 3\x00invalid database", self.key)}),
        }
        for failure, responses in failures.items():
            with (self.subTest(failure=failure), patch("requests.get", side_effect=responses),
                  self.assertRaises((OSError, ValueError, sqlite3.DatabaseError, zipfile.BadZipFile))):
                downloader.cloud_database(self.config)
            self.assertEqual((self.cache.read_bytes(), self.version.read_bytes()), previous)
        self.credentials.assert_not_called()

    def test_missing_or_empty_password_file_never_falls_back(self):
        previous = self.seed_cache()
        for contents in (None, b"\xef\xbb\xbf\r\n", b"\xff"):
            with self.subTest(contents=contents):
                if contents is None:
                    self.password_file.unlink()
                else:
                    self.password_file.write_bytes(contents)
                with (patch("requests.get", side_effect=self.responses()),
                      self.assertRaises((OSError, ValueError))):
                    downloader.cloud_database(self.config)
                self.assertEqual((self.cache.read_bytes(), self.version.read_bytes()), previous)
        self.credentials.assert_not_called()

    def test_version_publish_failure_restores_old_database(self):
        previous = self.seed_cache()
        with closing(sqlite3.connect(self.root/"source.db")) as database:
            database.execute("PRAGMA user_version = 1")
        self.plaintext = (self.root/"source.db").read_bytes()
        self.assertNotEqual(self.plaintext, previous[0])
        replace = Path.replace

        def fail_version(source, target):
            if Path(target) == self.version:
                raise OSError("fixture sidecar failure")
            return replace(source, target)

        with (patch("requests.get", side_effect=self.responses()),
              patch.object(Path, "replace", new=fail_version), self.assertRaises(OSError)):
            downloader.cloud_database(self.config)
        self.assertEqual((self.cache.read_bytes(), self.version.read_bytes()), previous)

    def test_uninitialized_branch_keeps_previous_cache(self):
        previous = self.seed_cache()
        with (patch("requests.get", side_effect=self.responses({"subscriptions.json": b"{}"})),
              redirect_stdout(io.StringIO())):
            self.assertIsNone(downloader.cloud_database(self.config))
        self.assertEqual((self.cache.read_bytes(), self.version.read_bytes()), previous)

    def test_default_database_path_and_credentials_are_unchanged(self):
        with (patch.object(downloader, "credentials", return_value=("student", "uis")) as credentials,
              patch("requests.get", side_effect=self.responses(
                  key=crypto_box.derive_custom_password("environment-password")))):
            result = downloader.cloud_database({"repository": "personal/repo"})
        self.assertEqual(result, self.runtime/"cloud.db")
        self.assertTrue((self.runtime/"cloud-version.json").is_file())
        credentials.assert_called_once_with()

    def test_previous_password_without_current_custom_still_needs_rekey(self):
        with (patch.object(downloader, "credentials", return_value=("student", "uis")),
              patch.dict(os.environ, {"DB_PASSWORD": ""}),
              patch("requests.get", side_effect=self.responses(
                  key=crypto_box.derive_custom_password("previous-password")))):
            config = {"repository": "personal/repo"}
            downloader.cloud_database(config)
        self.assertTrue(config["_needs_rekey"])

    def test_cloud_cli_is_isolated_on_success_and_failure(self):
        private_config = self.root/"private.json"
        private_config.write_text(json.dumps(self.config), encoding="utf-8-sig")
        for fail in (False, True):
            with self.subTest(fail=fail), ExitStack() as stack:
                blocked = [stack.enter_context(patch(target, side_effect=AssertionError(target)))
                           for target in ("replay_library.settings", "replay_library.run",
                                          "replay_library.write_json", "replay_library.transfer",
                                          "desktop.downloader.login", "desktop.downloader.download",
                                          "desktop.downloader.sync_subtitles", "desktop.downloader.download_video",
                                          "desktop.downloader.fetch_ppt")]
                lock = stack.enter_context(patch.object(lib, "queue_lock", wraps=lib.queue_lock))
                stack.enter_context(patch("sys.argv", ["replay_library.py", "cloud", "--config", str(private_config)]))
                stack.enter_context(patch("requests.get", side_effect=OSError("fixture") if fail else self.responses()))
                output = stack.enter_context(redirect_stdout(io.StringIO()))
                if fail:
                    with self.assertRaises(SystemExit) as error:
                        lib.main()
                    self.assertEqual(error.exception.code, 1)
                else:
                    lib.main()
                    self.assertEqual(json.loads(output.getvalue()), {"database": str(self.cache)})
                lock.assert_called_once_with(self.cache.with_name("cloud.db.lock"))
                for mock in blocked:
                    mock.assert_not_called()
                self.assertFalse(self.runtime.exists())
        self.assertEqual(lib.read_json(private_config), self.config)
        with lib.queue_lock(self.cache.with_name("cloud.db.lock")):
            pass

    def test_invalid_explicit_config_never_uses_personal_settings(self):
        config_file = self.root/"invalid.json"
        for contents in (None, "{", "[]", "null", "{}"):
            with self.subTest(contents=contents):
                if contents is not None:
                    config_file.write_text(contents, encoding="utf-8")
                with (patch("sys.argv", ["replay_library.py", "--config", str(config_file), "cloud"]),
                      patch.object(lib, "settings") as settings,
                      patch.object(lib, "write_json") as write,
                      patch("requests.get") as get,
                      redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()),
                      self.assertRaises(SystemExit)):
                    lib.main()
                settings.assert_not_called()
                write.assert_not_called()
                get.assert_not_called()
                self.assertFalse(self.runtime.exists())


if __name__ == "__main__":
    unittest.main()
