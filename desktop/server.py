"""Loopback-only course library; media requests support browser byte-range seeking."""
import functools
import json
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from urllib.parse import urlparse, unquote

from local_replay import RangeRequestHandler, ThreadingHTTPServer, write_json
from replay_library import BASE, RUNTIME, settings, roots, catalog, read_json


def make_app(port=8765):
    token = secrets.token_urlsafe(32)
    worker_lock = threading.Lock()
    child = [None]

    class Handler(RangeRequestHandler):
        def log_message(self, *_):
            pass

        def json_response(self, value, status=200):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers(); self.wfile.write(body)

        def translate_path(self, path):
            parts = unquote(urlparse(path).path).split("/")
            if len(parts) >= 4 and parts[1] == "media" and parts[2] in ("0", "1"):
                root = roots(settings())[int(parts[2])].resolve()
                target = root.joinpath(*parts[3:]).resolve()
                if target.is_relative_to(root) and not any(p.startswith(".") for p in parts[3:]):
                    return str(target)
            return str(BASE/"desktop"/"__missing__")

        def do_GET(self):
            if self.headers.get("Host") not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                self.send_error(403); return
            path = urlparse(self.path).path
            if path == "/api/library":
                cfg = settings()
                self.json_response({"courses": catalog(cfg), "settings": cfg,
                                    "configured": configured(), "token": token,
                                    "running": child[0] is not None and child[0].poll() is None,
                                    "last": read_json(RUNTIME/"last-run.json", {})})
            elif path == "/":
                body = (BASE/"desktop"/"index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers(); self.wfile.write(body)
            elif path.startswith("/media/"):
                target = Path(self.translate_path(self.path))
                if target.is_file() and target.suffix.lower() in (".mp4", ".vtt", ".jpg", ".png", ".json", ".jpeg"):
                    super().do_GET()
                else:
                    self.send_error(404)
            else:
                self.send_error(404)

        def do_POST(self):
            if self.headers.get("X-Course-Token") != token:
                self.json_response({"error": "请求无效，请刷新窗口"}, 403); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 16384:
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/settings":
                    cfg = settings()
                    for key in ("destination", "fallback", "transfer_time"):
                        if key in data:
                            cfg[key] = str(data[key]).strip()
                    import re
                    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cfg["transfer_time"]):
                        raise ValueError("转存时间格式应为 HH:MM")
                    if not Path(cfg["destination"]).is_absolute() or not Path(cfg["fallback"]).is_absolute():
                        raise ValueError("需要绝对路径")
                    if Path(cfg["destination"]).resolve() == Path(cfg["fallback"]).resolve():
                        raise ValueError("暂存目录不能与目标目录相同")
                    if "courses" in data:
                        from local_replay import course_id
                        cfg["courses"] = [course_id(v.strip()) for v in data["courses"].split(",") if v.strip()]
                    if data.get("password"):
                        from desktop.downloader import save_credentials
                        save_credentials(data["account"], data["password"])
                    write_json(RUNTIME/"settings.json", cfg)
                    if os.name == "nt":
                        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                        str(BASE/"desktop"/"install-tasks.ps1")],
                                       creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=30,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.json_response({"ok": True})
                elif self.path == "/api/run" and data.get("command") in ("download", "transfer", "subtitles"):
                    with worker_lock:
                        if child[0] is not None and child[0].poll() is None:
                            self.json_response({"error": "已有任务正在运行"}, 409); return
                        log = (RUNTIME/"worker.log").open("a", encoding="utf-8")
                        try:
                            child[0] = subprocess.Popen([sys.executable, "-u", str(BASE/"replay_library.py"), data["command"]],
                                                        cwd=BASE, stdout=log, stderr=log,
                                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                        finally:
                            log.close()
                    self.json_response({"ok": True})
                else:
                    self.json_response({"error": "未知操作"}, 404)
            except ValueError as e:
                self.json_response({"error": str(e) or "设置格式无效"}, 400)
            except Exception:
                self.json_response({"error": "操作未完成，请检查目录权限和任务状态"}, 500)

    mimetypes.add_type("text/vtt", ".vtt")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def configured():
    try:
        from desktop.downloader import credentials
        credentials()
        return True
    except Exception:
        return False


def serve():
    server = make_app(settings()["port"])
    print(f"课程库：http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
