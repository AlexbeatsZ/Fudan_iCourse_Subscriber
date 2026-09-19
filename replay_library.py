"""ROG download queue, verified network-drive transfers and cloud subtitles."""
from __future__ import annotations

import argparse
import contextlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

from local_replay import write_json

BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "local-data" / "rog"
def default_destination():
    if Path(r"E:\Videos").exists():
        return r"E:\Videos"
    return r"\\192.168.137.1\E\Videos"


DEFAULT = {"destination": default_destination(), "fallback": str(Path.home()/"Downloads"/"iCourse"),
           "repository": "AlexbeatsZ/Fudan_iCourse_Subscriber", "courses": ["37113"],
           "transfer_time": "22:00", "port": 8765}


def read_json(path, default=None):
    return json.loads(Path(path).read_text(encoding="utf-8-sig")) if Path(path).exists() else default


def settings():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    return DEFAULT | read_json(RUNTIME/"settings.json", {})


@contextlib.contextmanager
def queue_lock():
    """OS lock releases on process exit; no stale lock after power loss."""
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME/"queue.lock").open("a+b") as f:
        f.seek(0); f.write(b"0"); f.flush(); f.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("已有下载或转存任务正在运行") from None
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


def safe_name(name):
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name)).strip(" .")[:100]
    if not result or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", result):
        result = "课程_" + result
    return result


def lesson_stem(number):
    return f"第{int(number):02d}节"


def ordered_lectures(lectures):
    # Same-title duplicates are platform duplicates; prefer playable entry.
    seen = {}
    for item in sorted(lectures, key=lambda x: (x.get("date", ""), int(x["sub_id"]))):
        key = item.get("sub_title") or str(item["sub_id"])
        if key not in seen or (not seen[key].get("has_playback") and item.get("has_playback")):
            seen[key] = item
    return list(seen.values())


def ensure_network_share():
    if os.name == "nt":
        try:
            pwd = os.environ.get("OMEN_SMB_PASSWORD")
            if not pwd:
                import winreg
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                        pwd, _ = winreg.QueryValueEx(key, "OMEN_SMB_PASSWORD")
                except OSError:
                    pass
            user = os.environ.get("OMEN_SMB_USER", "Meta")
            cmd = ["net", "use", r"\\192.168.137.1\IPC$"]
            if pwd:
                cmd.extend([f"/user:{user}", pwd])
            import subprocess
            subprocess.run(cmd, capture_output=True, text=True)
        except Exception:
            pass


def writable(root):
    try:
        root = Path(root)
        if str(root).startswith(r"\\") or str(root).lower().startswith(("z:", "d:", "e:")):
            ensure_network_share()
        if not root.parent.exists():
            return False
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryFile(dir=root):
            pass
        return True
    except OSError:
        return False


def roots(config):
    return [Path(config["destination"]), Path(config["fallback"])]


def course_folder(root, title, cid):
    name = safe_name(title)
    folder = root/name
    meta = read_json(folder/"course.json", {})
    if (meta and meta.get("course_id") != cid) or (folder.exists() and not meta):
        folder = root/f"{name} ({cid})"
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder/"course.json", {"course_id": cid, "title": title})
    return folder


def video_complete(path):
    try:
        record = read_json(path.with_suffix(".mp4.json"), {})
        return path.is_file() and record.get("complete") and path.stat().st_size == record.get("total")
    except (OSError, ValueError):
        return False


def subtitle_text(segments):
    def stamp(ms):
        ms = round(ms)
        return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}.{ms%1000:03d}"

    def split_cues(text, start_ms, end_ms, max_len=26):
        text = text.replace("\r", " ").replace("\n", " ").strip()
        if not text:
            return []
        delimiters = r'([。！？!?；;\n]+|[，,、]+)'
        tokens = re.split(delimiters, text)
        raw_clauses = []
        curr = ""
        for tok in tokens:
            if not tok:
                continue
            if re.match(delimiters, tok):
                curr += tok
                raw_clauses.append(curr.strip())
                curr = ""
            else:
                curr += tok
        if curr.strip():
            raw_clauses.append(curr.strip())

        chunks = []
        buf = ""
        for cl in raw_clauses:
            if not cl:
                continue
            if not buf:
                buf = cl
            elif len(buf) + len(cl) <= max_len:
                buf += cl
            else:
                if len(cl) <= 6 and len(buf) + len(cl) <= max_len + 4:
                    buf += cl
                else:
                    chunks.append(buf)
                    buf = cl
        if buf:
            if len(buf) <= 6 and chunks and len(chunks[-1]) + len(buf) <= max_len + 5:
                chunks[-1] += buf
            else:
                chunks.append(buf)

        cues_text = []
        for ch in chunks:
            while len(ch) > max_len + 4:
                cues_text.append(ch[:max_len])
                ch = ch[max_len:]
            if ch:
                cues_text.append(ch)

        if not cues_text:
            return []
        if len(cues_text) == 1:
            return [(start_ms, end_ms, cues_text[0])]

        total_chars = sum(max(1, len(re.sub(r"[\s\W_]+", "", c)) or len(c)) for c in cues_text)
        total_dur = end_ms - start_ms

        results = []
        curr_start = start_ms
        for i, c in enumerate(cues_text):
            if i == len(cues_text) - 1:
                c_end = end_ms
            else:
                c_chars = max(1, len(re.sub(r"[\s\W_]+", "", c)) or len(c))
                dur = (c_chars / total_chars) * total_dur
                c_end = round(curr_start + dur)
            if c_end <= curr_start:
                c_end = curr_start + 100
            results.append((curr_start, c_end, c))
            curr_start = c_end
        return results

    lines = ["WEBVTT", ""]
    for seg in sorted(segments, key=lambda s: s["start_ms"]):
        start, end = float(seg["start_ms"]), float(seg["end_ms"])
        if not all(math.isfinite(v) for v in (start, end)) or start < 0 or end <= start:
            raise ValueError("字幕时间无效")
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        cues = split_cues(text, start, end)
        for c_start, c_end, c_text in cues:
            esc = html.escape(c_text).strip()
            if esc:
                lines.extend([f"{stamp(c_start)} --> {stamp(c_end)}", esc, ""])
    return "\n".join(lines) + "\n"


def catalog(config):
    ensure_network_share()
    result = []
    for root_index, root in enumerate(roots(config)):
        try:
            if not root.exists():
                continue
            folders = sorted(root.iterdir())
        except OSError:
            continue
        for folder in folders:
            if not folder.is_dir():
                continue
            lessons = []
            for video in sorted(folder.glob("*.mp4")):
                match = re.search(r"第?(\d+)节?", video.stem)
                num = int(match.group(1)) if match else 0
                meta = read_json(folder/(video.stem+".lesson.json"), {})
                lessons.append({"number": num, "name": video.stem, "video": video.name,
                                "subtitle": video.with_suffix(".vtt").exists(), **meta})
            if lessons:
                lessons.sort(key=lambda x: (x["number"] if x["number"] > 0 else 9999, x["name"]))
                result.append({"root": root_index, "folder": folder.name, "title": folder.name,
                               "staged": root_index == 1, "lessons": lessons})
    return result


def copy_verified(source, target):
    """Never replace unrelated content; byte-compare before clearing source."""
    import filecmp
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not filecmp.cmp(source, target, shallow=False):
            raise FileExistsError("目标存在不同内容，未覆盖")
        return
    temp = target.with_name(target.name+".transfer")
    with source.open("rb") as inp, temp.open("wb") as out:
        shutil.copyfileobj(inp, out, 4*1024*1024)
        out.flush(); os.fsync(out.fileno())
    if not filecmp.cmp(source, temp, shallow=False):
        raise OSError("转存校验失败，保留暂存文件")
    temp.replace(target)


def transfer(config):
    target_root, fallback = roots(config)
    if not writable(target_root):
        print("网络盘不可达，视频继续保留在下载文件夹", flush=True)
        return 0
    moved = 0
    for course in catalog(config):
        if not course["staged"]:
            continue
        source = fallback/course["folder"]
        info = read_json(source/"course.json", {})
        if not info.get("course_id"):
            continue
        target = course_folder(target_root, info["title"], info["course_id"])
        for lesson in course["lessons"]:
            stem = lesson["name"]
            if not video_complete(source/(stem+".mp4")):
                continue
            files = [p for p in source.glob(stem+".*") if p.is_file() and not p.name.endswith((".part", ".tmp", ".transfer"))]
            assets = source/(stem+".assets")
            if assets.exists():
                files += [p for p in assets.rglob("*") if p.is_file() and not p.name.endswith((".part", ".tmp"))]
            for file in files:
                copy_verified(file, target/file.relative_to(source))
            # Every file in this lesson is durable before deleting any source file.
            for file in files:
                file.unlink()
            if assets.exists() and not any(assets.iterdir()):
                assets.rmdir()
            moved += 1
    return moved


def run(command, only=None):
    config = settings()
    with queue_lock():
        if command == "download":
            from desktop.downloader import download, sync_subtitles
            errors = download(config, only)
            try:
                transfer(config)
            except Exception as e:
                errors.append("转存: "+type(e).__name__)
            try:
                sync_subtitles(config)
            except Exception as e:
                errors.append("字幕同步: "+type(e).__name__)
            return {"errors": errors}
        if command == "transfer":
            return {"transferred": transfer(config)}
        if command == "subtitles":
            from desktop.downloader import sync_subtitles
            return {"subtitles": sync_subtitles(config)}
        raise ValueError("未知命令")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["download", "transfer", "subtitles", "status", "app", "setup"])
    parser.add_argument("--lesson")
    parser.add_argument("--open", action="store_true", help="在浏览器中自动打开")
    args = parser.parse_args()
    if args.command == "app":
        from desktop.server import serve
        serve(open_browser=args.open)
    elif args.command == "setup":
        import getpass
        from desktop.downloader import save_credentials
        save_credentials(input("FUDAN_STUID: "), getpass.getpass("FUDAN_UISPSW: "))
        print("已保存到 Windows 用户环境变量")
    elif args.command == "status":
        print(json.dumps(catalog(settings()), ensure_ascii=False, indent=2))
    else:
        try:
            result = run(args.command, args.lesson)
            write_json(RUNTIME/"last-run.json", {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "command": args.command, **result})
            print(json.dumps(result, ensure_ascii=False))
            if result.get("errors"):
                raise SystemExit(1)
        except Exception as e:
            # Request exceptions can embed signed URLs. Never persist them.
            write_json(RUNTIME/"last-run.json", {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "command": args.command, "error": type(e).__name__})
            print("任务未完成，请检查设置或网络 ("+type(e).__name__+")")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
