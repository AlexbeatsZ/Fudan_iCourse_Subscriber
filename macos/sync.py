"""One-way SFTP archive pull. Video transport has no remote fallback."""
from __future__ import annotations
import argparse
import contextlib
import filecmp
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid

BASE = Path(__file__).resolve().parents[1]
RUNTIME = BASE / "local-data" / "mac"
LAN = "192.168.31.214"
REMOTE = "100.113.70.121"
SOURCE_ROOTS = {"videos": "D:/Videos", "elearning": "D:/Documents/Elearning"}
HELPER = "/c/Portable Programs/iCourse Player/app/mac_manifest.py"
PYTHON = "/c/Portable Programs/iCourse Player/runtime/python.exe"
DEFAULT = {"destination": str(Path.home() / "Movies" / "icouse"), "materials": str(Path.home() / "Documents" / "Elearning"), "port": 8765}


class Waiting(RuntimeError):
    pass


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def settings():
    return DEFAULT | read_json(RUNTIME / "settings.json", {})


def controls(kind):
    return read_json(RUNTIME / (kind + "-control.json"), {"paused": False, "revision": 0})


def control(kind, action):
    if kind not in {"videos", "elearning"} or action not in {"pause", "resume", "retry"}:
        raise ValueError("同步操作无效")
    current = controls(kind)
    current["paused"] = action == "pause"
    current["revision"] = current.get("revision", 0) + 1
    write_json(RUNTIME / (kind + "-control.json"), current)


def lan_interface():
    route = subprocess.run(["/sbin/route", "-n", "get", LAN], capture_output=True, text=True, timeout=3)
    fields = dict(re.findall(r"^\s*(\w+):\s*(.*)$", route.stdout, re.M))
    interface = fields.get("interface", "")
    if route.returncode or not re.fullmatch(r"en\d+", interface) or "GATEWAY" in fields.get("flags", ""):
        return None
    config = subprocess.run(["/sbin/ifconfig", interface], capture_output=True, text=True, timeout=3)
    for address, mask in re.findall(r"inet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-f]+)", config.stdout):
        network = ipaddress.IPv4Network((address, str(ipaddress.IPv4Address(int(mask, 16)))), strict=False)
        if ipaddress.ip_address(LAN) in network and ipaddress.ip_address(address) in ipaddress.ip_network("192.168.31.0/24"):
            return interface
    return None


def connection(kind):
    interface = lan_interface()
    if interface:
        return LAN, interface
    if kind == "videos":
        raise Waiting("等待宿舍局域网")
    return REMOTE, None


def ssh_options(host, interface):
    options = ["-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "ConnectionAttempts=1",
               "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlias=" + LAN,
               "-o", "ProxyCommand=none", "-o", "ProxyJump=none", "-o", "ControlMaster=no", "-o", "ControlPath=none",
               "-o", "ClearAllForwardings=yes", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2"]
    if interface:
        options += ["-o", "BindInterface=" + interface]
    return options


def guarded_command(argv, payload, kind, interface, tick=None):
    if controls(kind).get("paused"):
        raise Waiting("已暂停")
    if interface and lan_interface() != interface:
        raise Waiting("等待宿舍局域网")
    env = {k: v for k, v in os.environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}}
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    result = []
    thread = threading.Thread(target=lambda: result.append(process.communicate(payload.encode("utf-8"))), daemon=True)
    thread.start()
    failure = None
    started = time.monotonic()
    try:
        while thread.is_alive():
            thread.join(1)
            if controls(kind).get("paused"):
                failure = "已暂停"
            elif interface and lan_interface() != interface:
                failure = "等待宿舍局域网"
            elif kind == "videos" and not interface:
                failure = "等待宿舍局域网"
            if failure:
                process.terminate()
                break
            if tick:
                tick()
            if not tick and time.monotonic() - started > 90:
                failure = "源端清单请求超时"
                process.terminate()
                break
        thread.join(5)
    finally:
        if process.poll() is None:
            process.kill()
        thread.join(5)
    if failure:
        raise Waiting(failure)
    if not result or process.returncode:
        # Raw SSH errors might contain a filename; never contain campus credentials.
        raise Waiting("OMEN 连接或文件传输未完成（SSH/SFTP）")
    return result[0][0].decode("utf-8-sig")


def manifest(kind, host, interface, path=None):
    if kind == "videos" and (host != LAN or not interface):
        raise Waiting("等待宿舍局域网")
    command = shlex.quote(PYTHON) + " -X utf8 " + shlex.quote(HELPER) + " " + kind
    if path is not None:
        command += " --path " + shlex.quote(path)
    value = guarded_command(["/usr/bin/ssh", *ssh_options(host, interface), "meta@" + host, "bash -s"], command + "\n", kind, interface)
    return json.loads(value)


def local_path(root, relative):
    rel = PurePosixPath(relative)
    if not rel.parts or rel.is_absolute() or any(p in {".", ".."} or "\\" in p or ":" in p for p in rel.parts):
        raise ValueError("Invalid relative path")
    result = root.joinpath(*rel.parts)
    components = [root.joinpath(*rel.parts[:n]) for n in range(len(rel.parts) + 1)]
    if not result.resolve().is_relative_to(root.resolve()) or any(p.is_symlink() for p in components):
        raise ValueError("Local path outside archive")
    return result


def sftp_quote(value):
    value = str(value)
    if any(c in value for c in "\n\r\x00"):
        raise ValueError("SFTP path contains a command separator")
    # OpenSSH protects glob characters inside quoted paths itself. Escaping
    # brackets again requests a filename containing literal backslashes.
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def transfer_file(kind, host, interface, remote_root, row, partial, tick):
    if kind == "videos" and (host != LAN or not interface):
        raise Waiting("等待宿舍局域网")
    remote = "/" + remote_root.replace("\\", "/").rstrip("/") + "/" + row["path"]
    command = "reget" if partial.exists() and partial.stat().st_size else "get"
    payload = command + " " + sftp_quote(remote) + " " + sftp_quote(partial) + "\n"
    guarded_command(["/usr/bin/sftp", "-B", "262144", "-R", "64", "-b", "-", *ssh_options(host, interface), "meta@" + host], payload, kind, interface, tick)


def open_db(kind):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(RUNTIME / (kind + ".sqlite3"))
    db.execute("CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,size INTEGER,source_mtime INTEGER,local_size INTEGER,local_mtime INTEGER)")
    return db


def unchanged(db, row, target):
    old = db.execute("SELECT size,source_mtime,local_size,local_mtime FROM files WHERE path=?", (row["path"],)).fetchone()
    if not old or not target.is_file() or target.is_symlink():
        return False
    stat = target.stat()
    return old == (row["size"], row["mtime_ns"], stat.st_size, stat.st_mtime_ns)


def publish(db, row, partial, target, root):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or target.is_symlink():
            raise ValueError("目标不是普通文件")
        if filecmp.cmp(partial, target, shallow=False):
            partial.unlink()
        else:
            backup = root / ".icourse-sync" / "history" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]) / row["path"]
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.replace(backup)
            try:
                partial.replace(target)
            except Exception:
                backup.replace(target)
                raise
    else:
        partial.replace(target)
    os.utime(target, ns=(row["mtime_ns"], row["mtime_ns"]))
    stat = target.stat()
    with db:
        db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?)", (row["path"], row["size"], row["mtime_ns"], stat.st_size, stat.st_mtime_ns))


def sync_once(kind, limit=None, only_course=None):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    status_path = RUNTIME / (kind + "-status.json")
    previous = read_json(status_path, {})
    state = {"phase": "checking", "message": "检查源端资料", "time": time.time(), "kind": kind,
             "last_success": previous.get("last_success")}
    def update(**values):
        state.update(values)
        state["time"] = time.time()
        write_json(status_path, state)
    if controls(kind).get("paused"):
        update(phase="paused", message="已暂停")
        return
    cfg = settings()
    root = Path(cfg["destination"] if kind == "videos" else cfg["materials"])
    root.mkdir(parents=True, exist_ok=True)
    work = root / ".icourse-sync" / "partial"
    work.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / (kind + ".lock")).open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        db = open_db(kind)
        try:
            host, interface = connection(kind)
            update(network="局域网" if interface else "Tailscale", host=host)
            listing = manifest(kind, host, interface)
            if listing["root"] != SOURCE_ROOTS[kind]:
                raise ValueError("Source archive does not match the requested sync kind")
            for relative in listing.get("directories", []):
                local_path(root, relative).mkdir(parents=True, exist_ok=True)
            rows = listing["files"]
            if only_course:
                rows = [r for r in rows if r["path"].split("/")[0] == only_course]
            targets = [(r, local_path(root, r["path"])) for r in rows]
            pending = [(r, p) for r, p in targets if not unchanged(db, r, p)]
            total = sum(r["size"] for r, _ in pending)
            update(total_files=len(rows), pending_files=len(pending), pending_bytes=total, copied_files=0, completed_bytes=0)
            copied, completed = 0, 0
            for row, target in pending:
                if limit is not None and copied >= limit:
                    break
                key = hashlib.sha256(row["path"].encode()).hexdigest()[:32]  # Filename ID only; no content hashing.
                partial = work / (key + ".part")
                receipt = work / (key + ".json")
                if read_json(receipt, {}) != row or (partial.exists() and partial.stat().st_size > row["size"]):
                    partial.unlink(missing_ok=True)
                    write_json(receipt, row)
                if shutil.disk_usage(root).free < max(0, row["size"] - (partial.stat().st_size if partial.exists() else 0)) + 512 * 1024 * 1024:
                    raise Waiting("磁盘空间不足，已保留进度")
                started = time.monotonic()
                initial = partial.stat().st_size if partial.exists() else 0
                def tick():
                    current = partial.stat().st_size if partial.exists() else 0
                    update(phase="transferring", message="正在复制", file=row["path"], file_size=row["size"], file_bytes=current,
                           bytes_per_second=max(0, current-initial) / max(1, time.monotonic()-started))
                tick()
                transfer_file(kind, host, interface, listing["root"], row, partial, tick)
                if not partial.exists() or partial.stat().st_size != row["size"]:
                    raise Waiting("文件大小检查未通过，已保留进度")
                if manifest(kind, host, interface, row["path"]) != row:
                    partial.unlink(missing_ok=True)
                    receipt.unlink(missing_ok=True)
                    update(message="源文件已更新，下次检查重试此文件")
                    continue  # An actively updated sidecar must not hold up other courses.
                with partial.open("rb") as stream:
                    os.fsync(stream.fileno())
                publish(db, row, partial, target, root)
                receipt.unlink(missing_ok=True)
                copied += 1
                completed += row["size"]
                update(copied_files=copied, completed_bytes=completed, pending_files=len(pending)-copied, pending_bytes=total-completed)
            update(phase="idle", message="已同步" if copied == len(pending) else "本次复制完成，仍有待同步文件", last_success=time.time(), file=None, file_bytes=0)
        except Waiting as error:
            update(phase="paused" if controls(kind).get("paused") else "waiting", message=str(error))
        except Exception as error:
            update(phase="error", message="同步遇到错误（" + type(error).__name__ + "）")
            raise
        finally:
            db.close()


def watch(kind):
    while True:
        try:
            sync_once(kind)
        except Exception:
            pass
        revision = controls(kind).get("revision", 0)
        interface = lan_interface()
        for _ in range(150):
            time.sleep(2)
            if controls(kind).get("revision", 0) != revision or lan_interface() != interface:
                break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["videos", "elearning"])
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--course")
    args = parser.parse_args()
    if args.watch:
        watch(args.kind)
    else:
        sync_once(args.kind, args.limit, args.course)


if __name__ == "__main__":
    main()
