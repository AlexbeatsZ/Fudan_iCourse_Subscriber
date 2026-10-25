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
from scripts import bootstrap_data_branch as bootstrap
from src.data.subscriptions import (
    fetch_manifest, legacy_course_ids, manifest_bytes, parse_manifest,
)


class SubscriptionTests(unittest.TestCase):
    def test_bootstrap_creates_orphan_data_ref_with_public_empty_manifest(self):
        session = Mock()
        session.get.return_value = Mock(status_code=404)
        session.post.side_effect = [
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "tree"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "commit"}),
            Mock(status_code=201),
        ]
        self.assertTrue(bootstrap.ensure_data_branch("Friend/Fork", "token", session=session))
        tree_call, commit_call, ref_call = session.post.call_args_list
        self.assertEqual(tree_call.kwargs["json"]["tree"][0]["path"], "data/subscriptions.json")
        self.assertEqual(json.loads(tree_call.kwargs["json"]["tree"][0]["content"]),
                         {"course_ids": []})
        self.assertEqual(commit_call.kwargs["json"]["parents"], [])
        self.assertEqual(ref_call.kwargs["json"],
                         {"ref": "refs/heads/data", "sha": "commit"})
        self.assertIn("Friend/Fork", session.get.call_args.args[0])

    def test_bootstrap_can_seed_first_single_run_and_leaves_existing_data_alone(self):
        existing = Mock()
        existing.get.return_value = Mock(status_code=200)
        self.assertFalse(bootstrap.ensure_data_branch("Friend/Fork", "token", "1,2", session=existing))
        existing.post.assert_not_called()

        fresh = Mock()
        fresh.get.return_value = Mock(status_code=404)
        fresh.post.side_effect = [
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "tree"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "commit"}),
            Mock(status_code=201),
        ]
        self.assertTrue(bootstrap.ensure_data_branch("Friend/Fork", "token", "1,2,1", session=fresh))
        self.assertEqual(json.loads(fresh.post.call_args_list[0].kwargs["json"]["tree"][0]["content"]),
                         {"course_ids": ["1", "2"]})

    def test_bootstrap_race_succeeds_only_when_ref_now_exists(self):
        session = Mock()
        session.get.side_effect = [Mock(status_code=404), Mock(status_code=200)]
        session.post.side_effect = [
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "tree"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "commit"}),
            Mock(status_code=422),
        ]
        self.assertFalse(bootstrap.ensure_data_branch("Friend/Fork", "token", session=session))

        session.get.side_effect = [Mock(status_code=404), Mock(status_code=404)]
        session.post.side_effect = [
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "tree"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "commit"}),
            Mock(status_code=422, raise_for_status=Mock(side_effect=ValueError("422"))),
        ]
        with self.assertRaisesRegex(ValueError, "422"):
            bootstrap.ensure_data_branch("Friend/Fork", "token", session=session)

    def test_bootstrap_does_not_hide_permissions_or_missing_token(self):
        session = Mock()
        session.get.return_value = Mock(status_code=403,
                                        raise_for_status=Mock(side_effect=PermissionError("403")))
        with self.assertRaises(PermissionError):
            bootstrap.ensure_data_branch("Friend/Fork", "token", session=session)
        session.post.assert_not_called()
        with self.assertRaisesRegex(ValueError, "GITHUB_TOKEN"):
            bootstrap.ensure_data_branch("Friend/Fork", "", session=session)

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
    def test_first_fork_can_initialize_without_courses(self, _):
        self.assertEqual(resolver.resolve("Friend/Fork", "token", "check"),
                         ([], [], False))
        self.assertEqual(resolver.resolve("Friend/Fork", "token", "single", "4,5"),
                         (["4", "5"], ["4", "5"], True))
        self.assertEqual(resolver.resolve("Friend/Fork", "token", "single"),
                         ([], [], True))

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
