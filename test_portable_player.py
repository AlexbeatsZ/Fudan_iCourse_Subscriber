"""Integration checks for the independently deployable player."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, ProxyHandler, build_opener

from portable import player
from portable.export_player import player_html


class PortablePlayerTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(os.environ["LOCALAPPDATA"]) / "Temp" / ".agents"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="icourse-player-test-", dir=temp_root)
        self.root = Path(self.temp.name)
        self.media = self.root / "videos"
        folder = self.media / "Course"
        folder.mkdir(parents=True)
        (folder / "第01节.mp4").write_bytes(b"0123456789")
        (folder / "第01节.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:01.000\n字幕\n", encoding="utf-8")
        (folder / "第01节.lesson.json").write_text(json.dumps({"date": "2026-10-01", "video": "wrong.mp4"}), encoding="utf-8")
        (folder / "第02节.mp4").write_bytes(b"next lesson")
        (folder / "第02节.lesson.json").write_text("interrupted metadata", encoding="utf-8")
        assets = folder / "第01节.assets"
        assets.mkdir()
        (assets / "timeline.json").write_text('[{"time":0,"file":"001.jpg"},{"time":5,"file":"001.jpg"}]')
        (assets / "001.jpg").write_bytes(b"slide")
        (self.root / "app").mkdir()
        (self.root / "app" / "index.html").write_text("<!doctype html><title>Player</title>")
        (self.root / "settings.json").write_text(json.dumps({"destination": str(self.media), "port": 8765}))
        self.server = player.make_app(self.root, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = build_opener(ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def get(self, path, headers=None, method="GET"):
        return self.opener.open(Request(self.base + path, headers=headers or {}, method=method), timeout=5)

    def post(self, path, value, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Course-Token"] = token
        return self.opener.open(Request(self.base + path, data=json.dumps(value).encode(), headers=headers), timeout=5)

    def test_library_identities_and_timed_assets(self):
        with self.get("/api/library") as response:
            library = json.load(response)
        course = library["courses"][0]
        self.assertEqual((course["root"], course["folder"]), (0, "Course"))
        self.assertEqual([lesson["number"] for lesson in course["lessons"]], [1, 2])
        self.assertEqual(course["lessons"][0]["video"], "第01节.mp4")
        self.assertTrue(course["lessons"][0]["subtitle"])
        with self.get("/media/0/Course/" + quote("第01节.assets/timeline.json")) as response:
            self.assertEqual([page["time"] for page in json.load(response)], [0, 5])
        with self.get("/media/0/Course/" + quote("第01节.vtt")) as response:
            self.assertIn("text/vtt", response.headers["Content-Type"])
            self.assertIn("字幕", response.read().decode("utf-8"))

    def test_browser_seeking_head_and_invalid_range(self):
        path = "/media/0/Course/" + quote("第01节.mp4")
        for header, body, content_range in [("bytes=2-4", b"234", "bytes 2-4/10"),
                                             ("bytes=-3", b"789", "bytes 7-9/10"),
                                             ("bytes=8-", b"89", "bytes 8-9/10")]:
            with self.get(path, {"Range": header}) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.headers["Content-Range"], content_range)
                self.assertEqual(response.read(), body)
        with self.get(path, method="HEAD") as response:
            self.assertEqual(response.headers["Content-Length"], "10")
            self.assertEqual(response.read(), b"")
        with self.assertRaises(HTTPError) as raised:
            self.get(path, {"Range": "bytes=10-"})
        self.assertEqual(raised.exception.code, 416)
        self.assertEqual(raised.exception.headers["Content-Range"], "bytes */10")
        raised.exception.close()

    def test_media_and_host_boundaries(self):
        for path in ("/settings.json", "/media/0/Course/%2e%2e/%2e%2e/settings.json",
                     "/media/0/Course/%2e%2e%5c%2e%2e%5csettings.json", "/media/1/Course/file.mp4"):
            with self.assertRaises(HTTPError) as raised:
                self.get(path)
            self.assertEqual(raised.exception.code, 404)
            raised.exception.close()
        with self.assertRaises(HTTPError) as raised:
            self.get("/api/library", {"Host": "example.com"}, method="HEAD")
        self.assertEqual(raised.exception.code, 403)
        raised.exception.close()

    def test_settings_and_no_download_worker(self):
        with self.get("/api/library") as response:
            token = json.load(response)["token"]
        with self.assertRaises(HTTPError) as raised:
            self.post("/api/settings", {"destination": str(self.media)})
        self.assertEqual(raised.exception.code, 403)
        raised.exception.close()
        empty = self.root / "empty"
        empty.mkdir()
        with self.post("/api/settings", {"destination": str(empty)}, token) as response:
            self.assertTrue(json.load(response)["ok"])
        with self.get("/api/library") as response:
            self.assertEqual(json.load(response)["courses"], [])
        with self.assertRaises(HTTPError) as raised:
            self.post("/api/run", {"command": "download"}, token)
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()

    def test_export_keeps_playback_and_removes_remote_operations(self):
        source = (Path(__file__).parent / "desktop" / "index.html").read_text(encoding="utf-8")
        html = player_html(source)
        for required in ("last_played", "projection_alignment", "originalCues", "lightbox-next", "onended", "requestPictureInPicture"):
            self.assertIn(required, html)
        for absent in ("/api/run", 'id="download"', 'name="password"', "FUDAN_UISPSW", "管理课程"):
            self.assertNotIn(absent, html)


if __name__ == "__main__":
    unittest.main()
