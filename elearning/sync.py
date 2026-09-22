"""Incremental archive with local staging, atomic publication and SQLite state."""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import uuid

DEFAULT = {"destination": r"E:\Documents\Elearning", "courses": [],
           "times": ["00:00", "06:00", "12:00", "18:00"],
           "messages": True, "announcements": True}


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.flush()
        os.fsync(out.fileno())
    temp.replace(path)


def load_config(path):
    raw = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    result = DEFAULT | raw
    if not isinstance(result["courses"], list):
        raise ValueError("courses 必须是课程编号列表")
    result["courses"] = list(dict.fromkeys(course_id(x) for x in result["courses"]))
    if not result["times"] or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", x) for x in result["times"]):
        raise ValueError("times 必须是 HH:mm 时间列表")
    if not Path(result["destination"]).is_absolute():
        raise ValueError("destination 必须是绝对路径")
    return result


def course_id(value):
    match = re.fullmatch(r"(?:https://elearning\.fudan\.edu\.cn/courses/)?(\d+)/?(?:\?.*)?", str(value).strip())
    if not match:
        raise ValueError("课程编号或链接无效")
    return str(int(match[1]))


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")
    if not value or re.match(r"(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value):
        value = "_" + value
    suffix = Path(value).suffix[:20]
    if len(value) > 110:
        value = value[:110-len(suffix)] + suffix
    return value


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("目录超出归档范围")
    return path


@contextlib.contextmanager
def run_lock(runtime):
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "sync.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("已有 eLearning 任务正在运行") from None
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def open_db(runtime):
    runtime.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(runtime / "state.sqlite3")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS files (
          course TEXT, id TEXT, version TEXT, path TEXT, size INTEGER,
          mtime_ns INTEGER, PRIMARY KEY(course,id));
        CREATE TABLE IF NOT EXISTS names (
          scope TEXT, id TEXT, name TEXT, PRIMARY KEY(scope,id), UNIQUE(scope,name));
        CREATE TABLE IF NOT EXISTS notices (
          key TEXT PRIMARY KEY, version TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS events (
          id TEXT PRIMARY KEY, payload TEXT, delivered INTEGER DEFAULT 0);
    """)
    return db


def mapped_name(db, scope, identity, raw):
    """Stable case-insensitive names, including Windows sanitization collisions."""
    identity = str(identity)
    row = db.execute("SELECT name FROM names WHERE scope=? AND id=?", (scope, identity)).fetchone()
    if row:
        return row[0]
    used = {x[0].casefold() for x in db.execute("SELECT name FROM names WHERE scope=?", (scope,))}
    name = safe_name(raw)
    if name.casefold() in used or name.casefold() in {".elearning", ".history"}:
        p = Path(name)
        name = f"{p.stem} [{identity}]{p.suffix}"
    counter, base = 1, name
    while name.casefold() in used:
        name = f"{base} ({counter})"
        counter += 1
    with db:
        db.execute("INSERT INTO names VALUES (?,?,?)", (scope, identity, name))
    return name


def folder_paths(db, cid, folders):
    rows = {str(x["id"]): x for x in folders}
    paths = {}
    visiting = set()

    def resolve(fid):
        if fid in paths:
            return paths[fid]
        if fid in visiting or fid not in rows:
            raise ValueError("平台文件夹父级缺失或循环")
        visiting.add(fid)
        row = rows[fid]
        parent = row.get("parent_folder_id")
        if parent is None:
            path = Path()
        else:
            if str(parent) not in rows and row.get("full_name"):
                # Canvas can omit hidden ancestors while returning visible children.
                # full_name is the server's authoritative root-relative hierarchy.
                parts = row["full_name"].split("/")[1:]
                path = Path()
                for index, part in enumerate(parts):
                    scope = f"fallback:{cid}:" + "/".join(parts[:index])
                    path /= mapped_name(db, scope, part, part)
            else:
                parent_path = resolve(str(parent))
                name = mapped_name(db, f"node:{cid}:{parent}", "folder-" + fid, row["name"])
                path = parent_path / name
        visiting.remove(fid)
        paths[fid] = path
        return path

    for fid in rows:
        resolve(fid)
    return paths


def emit(db, kind, payload):
    event = {"id": str(uuid.uuid4()), "type": kind, "observed_at": now(), **payload}
    db.execute("INSERT INTO events(id,payload) VALUES (?,?)", (event["id"], json.dumps(event, ensure_ascii=False)))


def error_label(exc):
    # Transport exception messages can contain cookies or signed URLs.
    from .client import CanvasError
    return str(exc) if isinstance(exc, CanvasError) else type(exc).__name__


class Sync:
    def __init__(self, client, config, runtime):
        self.client, self.config, self.runtime = client, config, runtime
        self.root = Path(config["destination"])
        self.db = open_db(runtime)
        self.stats = {"downloaded": 0, "unchanged": 0, "unavailable": 0, "notices": 0, "errors": []}

    def close(self):
        self.db.close()

    def publish(self, staged, destination):
        """Verified copy before publication; previous content remains recoverable."""
        import filecmp
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".elearning-transfer")
        with staged.open("rb") as inp, temporary.open("wb") as out:
            shutil.copyfileobj(inp, out, 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        if not filecmp.cmp(staged, temporary, shallow=False):
            raise OSError("转存校验失败")
        if destination.exists():
            if filecmp.cmp(staged, destination, shallow=False):
                temporary.unlink()
                return
            archive = inside(self.root, Path(".elearning") / "history" / uuid.uuid4().hex / destination.relative_to(self.root))
            archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, archive)
            if not filecmp.cmp(destination, archive, shallow=False):
                raise OSError("旧版本备份校验失败")
        temporary.replace(destination)

    def file(self, cid, title, folder, paths, item):
        fid = str(item["id"])
        if item.get("locked_for_user") or item.get("hidden_for_user"):
            self.stats["unavailable"] += 1
            return
        parent = str(item["folder_id"])
        if parent not in paths:
            raise ValueError("文件所属目录未返回")
        filename = mapped_name(self.db, f"node:{cid}:{parent}", "file-" + fid, item.get("display_name") or item["filename"])
        relative = folder / paths[parent] / filename
        destination = inside(self.root, relative)
        version = json.dumps([item.get("updated_at"), item.get("modified_at"), item.get("uuid"), item["size"]])
        old = self.db.execute("SELECT version,path,size,mtime_ns FROM files WHERE course=? AND id=?", (cid, fid)).fetchone()
        if old and old[0] == version and old[1] == str(relative) and destination.is_file():
            stat = destination.stat()
            if stat.st_size == old[2] and stat.st_mtime_ns == old[3]:
                self.stats["unchanged"] += 1
                return
        staging = self.runtime / "staging" / cid
        staging.mkdir(parents=True, exist_ok=True)
        staged, receipt = staging / (fid + ".ready"), staging / (fid + ".json")
        metadata = json.loads(receipt.read_text()) if receipt.exists() else {}
        if not (staged.exists() and staged.stat().st_size == int(item["size"]) and metadata.get("version") == version):
            partial = staging / (fid + ".part")
            partial_receipt = staging / (fid + ".partial.json")
            previous = json.loads(partial_receipt.read_text()) if partial_receipt.exists() else {}
            if previous.get("version") != version:
                partial.unlink(missing_ok=True)
            write_json(partial_receipt, {"version": version})
            self.client.download(item, partial)
            partial.replace(staged)
            write_json(receipt, {"version": version})
            partial_receipt.unlink(missing_ok=True)
        self.publish(staged, destination)
        stat = destination.stat()
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)",
                            (cid, fid, version, str(relative), stat.st_size, stat.st_mtime_ns))
            emit(self.db, "file.updated" if old else "file.created", {
                "course_id": cid, "course": title, "file_id": fid,
                "path": str(relative), "size": stat.st_size,
            })
        staged.unlink()
        receipt.unlink(missing_ok=True)
        self.stats["downloaded"] += 1
        print(f"已保存 {relative}", flush=True)

    def notice(self, kind, identity, version, payload):
        key = f"{kind}:{identity}"
        old = self.db.execute("SELECT version FROM notices WHERE key=?", (key,)).fetchone()
        if old and old[0] == version:
            return
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO notices VALUES (?,?,?)",
                            (key, version, json.dumps(payload, ensure_ascii=False)))
            emit(self.db, kind, payload)
        self.stats["notices"] += 1

    def run(self):
        courses = {str(c["id"]): c for c in self.client.courses()}
        write_json(self.runtime / "courses.json", list(courses.values()))
        for cid in self.config["courses"]:
            try:
                course = courses.get(cid) or self.client.get(f"/api/v1/courses/{cid}")
                title = course["name"]
                folder = Path(mapped_name(self.db, "courses", cid, title))
                paths = folder_paths(self.db, cid, self.client.folders(cid))
                files = self.client.files(cid)
                for path in paths.values():
                    inside(self.root, folder / path).mkdir(parents=True, exist_ok=True)
                print(f"检查 {title}：{len(files)} 个文件", flush=True)
                for item in files:
                    try:
                        self.file(cid, title, folder, paths, item)
                    except Exception as exc:
                        self.stats["errors"].append(f"课程 {cid} 文件 {item['id']}: {error_label(exc)}")
                        print(self.stats["errors"][-1], flush=True)
                if self.config["announcements"]:
                    for item in self.client.announcements(cid):
                        payload = {"course_id": cid, "course": title, "announcement_id": str(item["id"]),
                                   "title": item.get("title", ""), "body_html": item.get("message", ""),
                                   "url": item.get("html_url", ""), "posted_at": item.get("posted_at")}
                        version = json.dumps([item.get("posted_at"), item.get("last_reply_at"), payload], sort_keys=True)
                        self.notice("announcement", f"{cid}:{item['id']}", version, payload)
            except Exception as exc:
                self.stats["errors"].append(f"课程 {cid}: {error_label(exc)}")
                print(self.stats["errors"][-1], flush=True)
        if self.config["messages"]:
            try:
                for item in self.client.conversations():
                    payload = {"conversation_id": str(item["id"]), "subject": item.get("subject", ""),
                               "last_message": item.get("last_message", ""),
                               "last_message_at": item.get("last_message_at"),
                               "unread": item.get("workflow_state") == "unread",
                               "context_code": item.get("context_code", "")}
                    version = json.dumps([item.get("last_message_at"), item.get("message_count"), item.get("last_message")])
                    self.notice("message", item["id"], version, payload)
            except Exception as exc:
                self.stats["errors"].append(f"站内讯息: {error_label(exc)}")
        self.stats["time"] = now()
        write_json(self.runtime / "last-run.json", self.stats)
        return self.stats
