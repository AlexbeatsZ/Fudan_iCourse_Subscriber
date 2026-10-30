"""Local portable player with material browsing and separate sync controls."""
import json
import mimetypes
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit, parse_qs

from portable.player import make_app
from macos.sync import RUNTIME, control, controls, settings, read_json, local_path


class Extension:
    def get(self, handler, path, head=False):
        if path == "/api/sync":
            handler.response({kind: {**read_json(RUNTIME / (kind + "-status.json"), {"phase": "waiting", "message": "等待首次同步"}),
                                      "paused": controls(kind).get("paused", False)} for kind in ("videos", "elearning")}, head=head)
            return True
        if path == "/api/materials":
            root = Path(settings()["materials"])
            query = parse_qs(urlsplit(handler.path).query)
            relative = query.get("path", [""])[0]
            try:
                folder = local_path(root, relative) if relative else root
                if any(part.startswith(".") for part in Path(relative).parts):
                    raise ValueError()
                rows = [{"name": p.name, "path": p.relative_to(root).as_posix(), "directory": p.is_dir(), "size": p.stat().st_size if p.is_file() else 0}
                        for p in folder.iterdir() if not p.name.startswith(".") and not p.is_symlink()]
                rows.sort(key=lambda r: (not r["directory"], r["name"]))
                handler.response({"path": relative, "files": rows}, head=head)
            except (OSError, ValueError):
                handler.response({"error": "资料目录不可用"}, 404, head=head)
            return True
        if path.startswith("/materials/"):
            try:
                relative = unquote(path[len("/materials/"):])
                if any(part.startswith(".") for part in Path(relative).parts):
                    raise ValueError()
                target = local_path(Path(settings()["materials"]), relative)
                if not target.is_file():
                    raise ValueError()
                # Never execute an arbitrary HTML/JS document in the player origin.
                content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                inline = target.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".gif"}
                handler.send_response(200)
                handler.send_header("Content-Type", content_type if inline else "application/octet-stream")
                handler.send_header("Content-Length", str(target.stat().st_size))
                handler.send_header("X-Content-Type-Options", "nosniff")
                handler.send_header("Content-Security-Policy", "sandbox")
                if not inline:
                    handler.send_header("Content-Disposition", "attachment")
                handler.end_headers()
                if not head:
                    with target.open("rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            handler.wfile.write(chunk)
            except (OSError, ValueError):
                handler.response({"error": "资料文件不可用"}, 404, head=head)
            return True
        return False

    def post(self, handler, path, data):
        if path == "/api/sync":
            control(data["kind"], data["action"])
            handler.response({"ok": True})
            return True
        if path == "/api/materials/open":
            relative = data["path"]
            if any(part.startswith(".") for part in Path(relative).parts):
                raise ValueError("资料路径无效")
            target = local_path(Path(settings()["materials"]), relative)
            if not target.is_file():
                raise ValueError("资料文件不存在")
            if target.suffix.lower() not in {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".png", ".jpg", ".jpeg"}:
                raise ValueError("此文件请使用下载链接保存")
            subprocess.Popen(["/usr/bin/open", str(target)])
            handler.response({"ok": True})
            return True
        return False


def main():
    server = make_app(RUNTIME, extension=Extension())
    print("Mac iCourse: http://127.0.0.1:" + str(server.server_port), flush=True)
    with server:
        server.serve_forever()


if __name__ == "__main__":
    main()
