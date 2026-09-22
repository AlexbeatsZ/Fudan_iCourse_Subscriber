from pathlib import Path
import tempfile
import unittest
from contextlib import closing

from elearning.client import Client, CanvasError
from elearning.notifications import dispatch
from elearning.sync import DEFAULT, Sync, folder_paths, inside, mapped_name, open_db, safe_name


class FakeClient:
    def __init__(self):
        self.content = b"first"
        self.calls = 0
        self.item = {"id": 5, "folder_id": 2, "display_name": "课件.pdf", "size": 5,
                     "updated_at": "one", "content-type": "application/pdf"}

    def courses(self):
        return [{"id": 7, "name": "测试课程"}]

    def folders(self, cid):
        return [{"id": 1, "parent_folder_id": None, "name": "course files"},
                {"id": 2, "parent_folder_id": 1, "name": "第一章"}]

    def files(self, cid):
        return [self.item]

    def download(self, item, target):
        self.calls += 1
        target.write_bytes(self.content)

    def announcements(self, cid):
        return [{"id": 11, "title": "通知", "message": "测试", "posted_at": "one"}]

    def conversations(self):
        return [{"id": 12, "subject": "讯息", "last_message_at": "one", "message_count": 1}]


class SyncTests(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.gettempdir()) / ".agents"
        base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.base = Path(self.temp.name)
        self.runtime = self.base / "runtime"
        self.dest = self.base / "archive"
        self.client = FakeClient()
        self.config = DEFAULT | {"destination": str(self.dest), "courses": ["7"]}

    def tearDown(self):
        self.temp.cleanup()

    def run_sync(self):
        sync = Sync(self.client, self.config, self.runtime)
        try:
            return sync.run()
        finally:
            sync.close()

    def test_tree_incremental_update_and_notification_dedup(self):
        self.assertEqual(self.run_sync()["downloaded"], 1)
        output = self.dest / "测试课程" / "第一章" / "课件.pdf"
        self.assertEqual(output.read_bytes(), b"first")
        self.assertEqual(self.run_sync()["unchanged"], 1)
        self.assertEqual(self.client.calls, 1)
        with closing(open_db(self.runtime)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 3)
        self.client.item["updated_at"] = "two"
        self.client.content = b"other"
        self.assertEqual(self.run_sync()["downloaded"], 1)
        self.assertEqual(output.read_bytes(), b"other")
        old = list((self.dest / ".elearning" / "history").rglob("*.pdf"))
        self.assertEqual(len(old), 1)
        self.assertEqual(old[0].read_bytes(), b"first")

    def test_failed_publish_reuses_complete_staging(self):
        sync = Sync(self.client, self.config, self.runtime)
        sync.publish = lambda *_: (_ for _ in ()).throw(OSError("disk offline"))
        result = sync.run()
        sync.close()
        self.assertEqual(len(result["errors"]), 1)
        self.assertTrue((self.runtime / "staging" / "7" / "5.ready").exists())
        self.assertEqual(self.run_sync()["downloaded"], 1)
        self.assertEqual(self.client.calls, 1)

    def test_local_edits_retained_and_missing_file_repaired(self):
        self.run_sync()
        output = self.dest / "测试课程" / "第一章" / "课件.pdf"
        output.write_bytes(b"user modification")
        self.run_sync()
        self.assertEqual(output.read_bytes(), b"first")
        self.assertEqual(next((self.dest / ".elearning" / "history").rglob("*.pdf")).read_bytes(), b"user modification")
        output.unlink()
        self.assertEqual(self.run_sync()["downloaded"], 1)

    def test_locked_files_not_downloaded(self):
        self.client.item["locked_for_user"] = True
        result = self.run_sync()
        self.assertEqual(result["unavailable"], 1)
        self.assertEqual(self.client.calls, 0)

    def test_names_collision_and_path_escape(self):
        with closing(open_db(self.runtime)) as db:
            one = mapped_name(db, "scope", "1", "A:B.pdf")
            two = mapped_name(db, "scope", "2", "a?b.pdf")
            self.assertNotEqual(one.casefold(), two.casefold())
            self.assertEqual(two, mapped_name(db, "scope", "2", "changed"))
            with self.assertRaises(ValueError):
                folder_paths(db, "7", [{"id": 1, "parent_folder_id": 2, "name": "x"}, {"id": 2, "parent_folder_id": 1, "name": "y"}])
        with self.assertRaises(ValueError):
            inside(self.dest, "../escape")
        self.assertEqual(safe_name("CON.txt"), "_CON.txt")

    def test_delivery_failure_keeps_pending_events(self):
        self.run_sync()
        class Sender:
            def send(self, event):
                raise OSError("offline")
        with closing(open_db(self.runtime)) as db:
            with self.assertRaises(OSError):
                dispatch(db, Sender())
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE delivered=0").fetchone()[0], 3)
            sent = []
            sender = Sender()
            sender.send = sent.append
            self.assertEqual(dispatch(db, sender), 3)
            self.assertEqual(dispatch(db, sender), 0)


class ApiTests(unittest.TestCase):
    def test_pagination_and_cross_host_rejection(self):
        client = Client()
        class Response:
            def __init__(self, rows, links):
                self.rows, self.links = rows, links
            def json(self):
                return self.rows
        calls = []
        def request(method, path, **kwargs):
            calls.append(path)
            return (Response([{"id": 1}], {"next": {"url": "https://elearning.fudan.edu.cn/api/v1/courses?page=2"}})
                    if len(calls) == 1 else Response([{"id": 2}], {}))
        client.request = request
        self.assertEqual([x["id"] for x in client.pages("/api/v1/courses")], [1, 2])
        with self.assertRaises(CanvasError):
            client._url("https://other.example/api")
        client.close()

    def test_send_is_never_implicit(self):
        client = Client()
        with self.assertRaises(ValueError):
            client.send_message([1], "subject", "body")
        client.close()


if __name__ == "__main__":
    unittest.main()
