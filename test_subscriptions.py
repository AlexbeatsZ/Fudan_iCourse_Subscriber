"""First-run subscription bootstrap, legacy migration, and fork isolation."""
import base64
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from scripts import resolve_subscriptions as resolver
from src.data.subscriptions import (
    fetch_manifest, legacy_course_ids, manifest_bytes, parse_manifest,
)


class SubscriptionTests(unittest.TestCase):
    def test_manifest_roundtrip_and_deduplication(self):
        content = manifest_bytes(["40243", "38135", "40243"])
        self.assertEqual(json.loads(content)["course_ids"], ["40243", "38135"])
        self.assertEqual(parse_manifest(content), ["40243", "38135"])
        self.assertEqual(parse_manifest(manifest_bytes([])), [])

    def test_invalid_manifest_never_silently_discards_ids(self):
        for content in (b"[]", b"{}", b'{"course_ids": "1,2"}',
                        b'{"course_ids":["abc"]}', b"not json"):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_manifest(content)

    def test_fresh_fork_is_detected_with_git_ref_404(self):
        response = Mock(status_code=404)
        get = Mock(return_value=response)
        self.assertEqual(fetch_manifest("Friend/Fork", "token", get=get), (None, False))
        self.assertEqual(get.call_args.args[0],
                         "https://api.github.com/repos/Friend/Fork/git/ref/heads/data")

    def test_existing_manifest_is_loaded_from_current_repository_only(self):
        blob = manifest_bytes(["23", "42"])
        get = Mock(side_effect=[Mock(status_code=200, raise_for_status=Mock()),
                               Mock(status_code=200, raise_for_status=Mock(),
                                    json=lambda: {"encoding": "base64",
                                                  "content": base64.b64encode(blob).decode()})])
        self.assertEqual(fetch_manifest("Friend/Fork", "token", get=get),
                         (["23", "42"], True))
        self.assertIn("Friend/Fork", get.call_args.args[0])

    def test_http_422_or_403_are_not_treated_as_missing_branch(self):
        for code in (422, 403):
            response = requests.Response()
            response.status_code = code
            response.url = "https://api.github.com/repos/Friend/Fork/git/ref/heads/data"
            with self.subTest(code=code), self.assertRaises(requests.HTTPError):
                fetch_manifest("Friend/Fork", "token", get=lambda *a, **kw: response)

    def test_existing_db_subscription_meta_migrates(self):
        with tempfile.TemporaryDirectory() as directory:
            dbpath = Path(directory) / "old.db"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
                db.execute("INSERT INTO meta VALUES ('subscribed_course_ids', '101,202,101')")
            self.assertEqual(legacy_course_ids(dbpath), ["101", "202"])

    @patch.object(resolver, "fetch_manifest", return_value=(None, False))
    def test_first_fork_requires_single_run_course_input(self, _):
        self.assertEqual(resolver.resolve("Friend/Fork", "token", "check"),
                         ([], [], False))
        self.assertEqual(resolver.resolve("Friend/Fork", "token", "single", "4,5"),
                         (["4", "5"], ["4", "5"], True))
        with self.assertRaisesRegex(ValueError, "enter course IDs"):
            resolver.resolve("Friend/Fork", "token", "single")

    @patch.object(resolver, "fetch_manifest", return_value=(["11", "22"], True))
    def test_one_off_input_never_replaces_saved_subscriptions(self, _):
        self.assertEqual(resolver.resolve("Friend/Fork", "token", "single", "999"),
                         (["999"], ["11", "22"], False))
        self.assertEqual(resolver.resolve("Friend/Fork", "token", "check"),
                         (["11", "22"], ["11", "22"], False))

    @patch.object(resolver, "fetch_manifest", return_value=([], True))
    def test_empty_manifest_intentionally_disables_scheduled_probe(self, _):
        self.assertEqual(resolver.resolve("Friend/Fork", "token", "check"),
                         ([], [], False))

    @patch.object(resolver, "fetch_manifest", return_value=(None, True))
    def test_legacy_database_is_migrated_without_old_secret(self, _):
        with tempfile.TemporaryDirectory() as directory:
            dbpath = Path(directory) / "existing.db"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
                db.execute("INSERT INTO meta VALUES ('subscribed_course_ids', '10,20')")
            with patch("desktop.downloader.cloud_database", return_value=dbpath) as cloud:
                self.assertEqual(resolver.resolve("Friend/Fork", "token", "check"),
                                 (["10", "20"], ["10", "20"], True))
            cloud.assert_called_once_with({"repository": "Friend/Fork"})


if __name__ == "__main__":
    unittest.main()
