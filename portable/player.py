"""Independent local iCourse player. Python standard library only."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import unquote, urlsplit


APPLICATION = "icourse-portable-player"
VERSION = "1.0.0"
DEFAULT_SETTINGS = {"destination": r"D:\Videos", "port": 8765}
MEDIA_TYPES = {".mp4": "video/mp4", ".vtt": "text/vtt; charset=utf-8",
               ".json": "application/json; charset=utf-8",
               ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def settings(directory):
    saved = read_json(directory / "settings.json", {})
    return DEFAULT_SETTINGS | (saved if isinstance(saved, dict) else {})


def catalog(config):
    """Match the original player's folder and lesson identities for saved progress."""
    root = Path(config["destination"])
    try:
        folders = sorted(root.iterdir())
    except OSError:
        return []
    courses = []
    for folder in folders:
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        lessons = []
        for video in sorted(folder.glob("*.mp4")):
            if not video.is_file():
                continue
            match = re.search(r"第?(\d+)节?", video.stem)
            meta = read_json(video.with_suffix(".lesson.json"), {})
            meta = meta if isinstance(meta, dict) else {}
            lessons.append({**meta, "number": int(match[1]) if match else 0,
                            "name": video.stem, "video": video.name,
                            "subtitle": video.with_suffix(".vtt").is_file()})
        if lessons:
            lessons.sort(key=lambda item: (item["number"] or 9999, item["name"]))
            courses.append({"root": 0, "folder": folder.name, "title": folder.name,
                            "staged": False, "lessons": lessons})
    return courses


def make_app(directory, port=None):
    directory = Path(directory).resolve()
    token = secrets.token_urlsafe(32)
    settings_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Chromium may abandon an idle keep-alive connection.

        def log_message(self, *_):
            pass

        def valid_host(self):
            return self.headers.get("Host") in (
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}")

        def response(self, body, status=200, content_type="application/json; charset=utf-8", head=False):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def media_path(self, path):
            parts = unquote(path).split("/")
            if len(parts) < 5 or parts[1:3] != ["media", "0"]:
                return None
            if any(not part or part.startswith(".") or "\\" in part or ":" in part for part in parts[3:]):
                return None
            root = Path(settings(directory)["destination"]).resolve()
            target = root.joinpath(*parts[3:]).resolve()
            if target.is_relative_to(root) and target.is_file() and target.suffix.lower() in MEDIA_TYPES:
                return target
            return None

        def send_media(self, target, head=False):
            with target.open("rb") as stream:
                size = os.fstat(stream.fileno()).st_size
                start, end = 0, size - 1
                header = self.headers.get("Range")
                if header:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
                    if not match or not (match[1] or match[2]):
                        start = size
                    elif match[1]:
                        start = int(match[1])
                        end = min(int(match[2]) if match[2] else end, end)
                    else:
                        start = max(0, size - int(match[2]))
                    if start >= size or start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                length = max(0, end - start + 1)
                self.send_response(206 if header else 200)
                self.send_header("Content-Type", MEDIA_TYPES[target.suffix.lower()])
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                if header:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Last-Modified", self.date_time_string(target.stat().st_mtime))
                self.end_headers()
                if not head:
                    stream.seek(start)
                    while length:
                        chunk = stream.read(min(1024 * 1024, length))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        length -= len(chunk)

        def get(self, head=False):
            if not self.valid_host():
                self.response({"error": "Invalid host"}, 403, head=head)
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    self.response({"application": APPLICATION, "version": VERSION,
                                   "directory": str(directory), "pid": os.getpid()}, head=head)
                elif path == "/api/library":
                    cfg = settings(directory)
                    self.response({"courses": catalog(cfg), "settings": cfg, "token": token,
                                   "configured": True, "running": False, "last": {}}, head=head)
                elif path == "/":
                    self.response((directory / "app" / "index.html").read_bytes(),
                                  content_type="text/html; charset=utf-8", head=head)
                elif path.startswith("/media/"):
                    target = self.media_path(path)
                    if target:
                        self.send_media(target, head)
                    else:
                        self.response({"error": "Not found"}, 404, head=head)
                else:
                    self.response({"error": "Not found"}, 404, head=head)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Browser seeks cancel the preceding media request.
            except OSError:
                self.close_connection = True

        def do_GET(self):
            self.get()

        def do_HEAD(self):
            self.get(head=True)

        def do_POST(self):
            if not self.valid_host() or self.headers.get("X-Course-Token") != token:
                self.close_connection = True
                self.response({"error": "请求无效，请刷新窗口"}, 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 16384:
                    raise ValueError("设置格式无效")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/settings":
                    destination = str(data["destination"]).strip()
                    if not Path(destination).is_absolute():
                        raise ValueError("视频目录需要绝对路径")
                    with settings_lock:
                        cfg = settings(directory)
                        cfg["destination"] = destination
                        pending = directory / "settings.json.tmp"
                        pending.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        pending.replace(directory / "settings.json")
                    self.response({"ok": True})
                elif self.path == "/api/shutdown":
                    self.response({"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self.response({"error": "未知操作"}, 404)
            except (ValueError, KeyError, TypeError) as error:
                self.response({"error": str(error) or "设置格式无效"}, 400)
            except OSError:
                self.response({"error": "无法保存设置，请检查目录权限"}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", settings(directory)["port"] if port is None else port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    with make_app(args.directory) as server:
        print(f"iCourse Player: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
