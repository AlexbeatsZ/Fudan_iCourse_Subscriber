"""Regression coverage for fresh forks and independent database passwords."""
import gzip
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import replay_library
from scripts import db_shard
from src.data import crypto_box
from src.data.database import Database


class ForkSettingsTests(unittest.TestCase):
    def test_no_personal_courses_and_local_clone_repository_detection(self):
        self.assertEqual(replay_library.DEFAULT["courses"], [])
        with (patch.dict(os.environ, {"GITHUB_REPOSITORY": ""}),
              patch.object(replay_library.subprocess, "run",
                           return_value=Mock(stdout="https://github.com/Friend/Copy.git\n"))):
            self.assertEqual(replay_library.default_repository(), "Friend/Copy")

    def test_actions_always_uses_the_current_fork(self):
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory)
            replay_library.write_json(
                config_dir / "settings.json",
                {"repository": "AlexbeatsZ/Fudan_iCourse_Subscriber"},
            )
            with (patch.object(replay_library, "RUNTIME", config_dir),
                  patch.dict(os.environ, {
                      "GITHUB_ACTIONS": "true",
                      "GITHUB_REPOSITORY": "Friend/Fudan_iCourse_Subscriber",
                  })):
                self.assertEqual(
                    replay_library.settings()["repository"],
                    "Friend/Fudan_iCourse_Subscriber",
                )

    def test_actions_requires_repository_name(self):
        with tempfile.TemporaryDirectory() as directory:
            with (patch.object(replay_library, "RUNTIME", Path(directory)),
                  patch.dict(os.environ, {
                      "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "",
                  }),
                  self.assertRaisesRegex(RuntimeError, "GITHUB_REPOSITORY")):
                replay_library.settings()


class DatabasePasswordTests(unittest.TestCase):
    def test_new_key_fallback_and_wrong_password(self):
        original = b"SQLite format 3\x00" + b"test-data"
        v2 = crypto_box.encrypt(
            original, crypto_box.derive_new_password("student", "uis")
        )
        result, label = crypto_box.decrypt_with_fallback(
            v2, stuid="student", uispsw="uis", db_password="new-independent",
            validate=crypto_box.is_sqlite,
        )
        self.assertEqual((result, label), (original, "v2"))
        custom = crypto_box.encrypt(
            original, crypto_box.derive_custom_password("new-independent")
        )
        result, label = crypto_box.decrypt_with_fallback(
            custom, stuid="", uispsw="", db_password="new-independent",
            validate=crypto_box.is_sqlite,
        )
        self.assertEqual((result, label), (original, "custom"))
        with self.assertRaisesRegex(ValueError, "decryption failed"):
            crypto_box.decrypt_with_fallback(
                custom, stuid="student", uispsw="uis",
                db_password="wrong-independent", validate=crypto_box.is_sqlite,
            )

    def test_legacy_format_can_be_migrated(self):
        original = b"SQLite format 3\x00" + b"rest-of-test-data"
        old_key = crypto_box.derive_legacy_password("s", "u", "d", "mail")
        encrypted = crypto_box.encrypt(
            gzip.compress(original), old_key, crypto_box.LEGACY_ITERATIONS,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "legacy.enc").write_bytes(encrypted)
            with patch.dict(os.environ, {
                "STUID": "s", "UISPSW": "u",
                "DASHSCOPE_API_KEY": "d", "SMTP_PASSWORD": "mail",
                "DB_PASSWORD": "new-db-password",
            }, clear=True):
                db_shard._cmd_decode_legacy(str(root / "legacy.enc"), str(root / "out.db"))
            self.assertEqual((root / "out.db").read_bytes(), original)

    def test_shards_rekey_from_v2_and_rotate_custom_password(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database(str(root / "input.db"))
            database.upsert_course("123", "A course", "Teacher")
            database.conn.close()
            old_shards = root / "old"
            first_db = root / "first.db"
            new_shards = root / "new"
            rotated_db = root / "rotated.db"
            marker = root / "github_output"

            with patch.dict(os.environ, {
                "STUID": "student", "UISPSW": "uis", "DB_PASSWORD": "",
            }, clear=True):
                db_shard._cmd_shard(str(root / "input.db"), str(old_shards))

            with patch.dict(os.environ, {
                "STUID": "student", "UISPSW": "uis",
                "DB_PASSWORD": "independent-1", "GITHUB_OUTPUT": str(marker),
            }, clear=True):
                db_shard._cmd_reassemble(str(old_shards), str(first_db))
                self.assertIn("needs_rekey=true", marker.read_text())
                db_shard._cmd_shard(str(first_db), str(new_shards))

            with patch.dict(os.environ, {
                "DB_PASSWORD": "independent-2",
                "DB_PASSWORD_PREVIOUS": "independent-1",
            }, clear=True):
                db_shard._cmd_reassemble(str(new_shards), str(rotated_db))

            with sqlite3.connect(rotated_db) as conn:
                self.assertEqual(
                    conn.execute("SELECT title FROM courses WHERE course_id='123'").fetchone()[0],
                    "A course",
                )
            with patch.dict(os.environ, {"DB_PASSWORD": "wrong"}, clear=True):
                with self.assertRaisesRegex(ValueError, "Cannot decrypt"):
                    db_shard._cmd_reassemble(str(new_shards), str(root / "bad.db"))


if __name__ == "__main__":
    unittest.main()
