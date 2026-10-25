"""First-run subscription bootstrap, legacy migration, and fork isolation."""
import base64
import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from scripts import resolve_subscriptions as resolver
from scripts import bootstrap_data_branch as bootstrap
from desktop import downloader
from src.data import crypto_box
from src.data.subscriptions import (
    fetch_manifest, legacy_course_ids, manifest_bytes, parse_manifest,
)


class SubscriptionTests(unittest.TestCase):
    def test_bootstrap_creates_orphan_branch_with_manifest_and_encrypted_db(self):
        session = Mock()
        session.get.return_value = Mock(status_code=404)
        session.post.side_effect = [
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "blob1"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "blob2"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "tree"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "commit"}),
            Mock(status_code=201),
        ]
        with patch.object(bootstrap, "_new_database_files", return_value={
                "data/icourse-index.enc": b"encrypted-index",
                "data/shards/meta-0000.db.gz.enc": b"encrypted-shard"}):
            self.assertTrue(bootstrap.ensure_data_branch(
                "Friend/Fork", "token", session=session, stuid="s", uispsw="p"))
        blob1, blob2, tree_call, commit_call, ref_call = session.post.call_args_list
        self.assertEqual(base64.b64decode(blob1.kwargs["json"]["content"]), b"encrypted-index")
        self.assertEqual(base64.b64decode(blob2.kwargs["json"]["content"]), b"encrypted-shard")
        entries = tree_call.kwargs["json"]["tree"]
        self.assertEqual({entry["path"] for entry in entries}, {
            "data/subscriptions.json", "data/icourse-index.enc", "data/shards/meta-0000.db.gz.enc"})
        manifest_entry = next(item for item in entries if item["path"] == "data/subscriptions.json")
        self.assertEqual(json.loads(manifest_entry["content"]),
                         {"course_ids": []})
        self.assertEqual(commit_call.kwargs["json"]["parents"], [])
        self.assertEqual(ref_call.kwargs["json"],
                         {"ref": "refs/heads/data", "sha": "commit"})
        self.assertIn("Friend/Fork", session.get.call_args.args[0])

    def test_bootstrap_generates_decryptable_complete_empty_database(self):
        files = bootstrap._new_database_files(
            ["1", "2"], stuid="student", uispsw="uis", db_password="separate-secret")
        self.assertEqual(set(files), {"data/icourse-index.enc", "data/shards/meta-0000.db.gz.enc"})
        index = crypto_box.decrypt(
            files["data/icourse-index.enc"],
            crypto_box.derive_custom_password("separate-secret"))
        self.assertTrue(json.loads(index)["shards"])
        self.assertNotIn(b"separate-secret", files["data/icourse-index.enc"])

    def test_bootstrap_encrypted_files_roundtrip_into_cloud_database(self):
        import io
        import zipfile
        files = bootstrap._new_database_files(
            [], stuid="student", uispsw="uis", db_password="custom-secret")
        files["data/subscriptions.json"] = manifest_bytes([])
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, "w") as z:
            for path, content in files.items():
                z.writestr(f"fork-commit/{path}", content)
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(downloader, "RUNTIME", Path(directory)),
              patch.object(downloader, "credentials", return_value=("student", "uis")),
              patch.dict(os.environ, {"DB_PASSWORD": "custom-secret"}),
              patch("requests.get", side_effect=[
                  Mock(json=lambda: {"object": {"sha": "commit"}}),
                  Mock(content=zipped.getvalue()),
              ])):
            config = {"repository": "Friend/Fork"}
            dbpath = downloader.cloud_database(config)
            self.assertFalse(config["_needs_rekey"])
            with sqlite3.connect(dbpath) as db:
                self.assertIn("courses", {r[0] for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")})

    def test_bootstrap_leaves_complete_data_alone(self):
        existing = Mock()
        existing.get.side_effect = [
            Mock(status_code=200, json=lambda: {"object": {"sha": "old"}}),
            Mock(json=lambda: {"tree": {"sha": "oldtree"}}),
            Mock(json=lambda: {"tree": [
                {"path": "data/subscriptions.json", "type": "blob"},
                {"path": "data/icourse-index.enc", "type": "blob"},
                {"path": "data/shards/meta-0000.db.gz.enc", "type": "blob"},
            ]}),
        ]
        self.assertFalse(bootstrap.ensure_data_branch("Friend/Fork", "token", "1,2", session=existing))
        existing.post.assert_not_called()

    def test_bootstrap_can_seed_first_single_run(self):
        fresh = Mock()
        fresh.get.return_value = Mock(status_code=404)
        fresh.post.side_effect = [
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "blob"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "tree"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "commit"}),
            Mock(status_code=201),
        ]
        with patch.object(bootstrap, "_new_database_files", return_value={
                "data/icourse-index.enc": b"encrypted"}):
            self.assertTrue(bootstrap.ensure_data_branch("Friend/Fork", "token", "1,2,1",
                                                         session=fresh, db_password="secret"))
        self.assertEqual(json.loads(fresh.post.call_args_list[1].kwargs["json"]["tree"][0]["content"]),
                         {"course_ids": ["1", "2"]})

    def test_bootstrap_repairs_existing_manifest_only_branch_without_overwriting_it(self):
        session = Mock()
        session.get.side_effect = [
            Mock(status_code=200, json=lambda: {"object": {"sha": "old"}}),
            Mock(json=lambda: {"tree": {"sha": "oldtree"}}),
            Mock(json=lambda: {"tree": [
                {"path": "data/subscriptions.json", "type": "blob"},
            ]}),
        ]
        session.post.side_effect = [
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "blob"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "tree"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "commit"}),
        ]
        session.patch.return_value = Mock(status_code=200)
        with patch.object(bootstrap, "_new_database_files", return_value={
                "data/icourse-index.enc": b"encrypted"}):
            self.assertTrue(bootstrap.ensure_data_branch(
                "Friend/Fork", "token", session=session, db_password="secret"))
        tree_call = session.post.call_args_list[1]
        self.assertEqual(tree_call.kwargs["json"]["base_tree"], "oldtree")
        self.assertEqual([x["path"] for x in tree_call.kwargs["json"]["tree"]],
                         ["data/icourse-index.enc"])
        self.assertEqual(session.post.call_args_list[2].kwargs["json"]["parents"], ["old"])
        self.assertEqual(session.patch.call_args.kwargs["json"]["force"], False)

    def test_bootstrap_does_not_replace_orphan_encrypted_shards(self):
        session = Mock()
        session.get.side_effect = [
            Mock(status_code=200, json=lambda: {"object": {"sha": "old"}}),
            Mock(json=lambda: {"tree": {"sha": "oldtree"}}),
            Mock(json=lambda: {"tree": [
                {"path": "data/subscriptions.json", "type": "blob"},
                {"path": "data/shards/meta-0000.db.gz.enc", "type": "blob"},
            ]}),
        ]
        with self.assertRaisesRegex(FileNotFoundError, "no index"):
            bootstrap.ensure_data_branch("Friend/Fork", "token", session=session)
        session.post.assert_not_called()

    def test_bootstrap_preserves_old_database_subscriptions_during_migration(self):
        session = Mock()
        session.get.side_effect = [
            Mock(status_code=200, json=lambda: {"object": {"sha": "old"}}),
            Mock(json=lambda: {"tree": {"sha": "oldtree"}}),
            Mock(json=lambda: {"tree": [
                {"path": "data/icourse-index.enc", "type": "blob"},
                {"path": "data/shards/meta-0000.db.gz.enc", "type": "blob"},
            ]}),
        ]
        session.post.side_effect = [
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "tree"}),
            Mock(raise_for_status=Mock(), json=lambda: {"sha": "commit"}),
        ]
        session.patch.return_value = Mock(status_code=200)
        with patch.object(bootstrap, "_migrate_subscriptions", return_value=["9", "8"]) as migrate:
            self.assertTrue(bootstrap.ensure_data_branch("Friend/Fork", "token", session=session))
        migrate.assert_called_once_with("Friend/Fork")
        entries = session.post.call_args_list[0].kwargs["json"]["tree"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(json.loads(entries[0]["content"]), {"course_ids": ["9", "8"]})

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
