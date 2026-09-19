from contextlib import closing
"""ROG video downloads and small encrypted cloud transcript synchronization."""
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import zipfile

from local_replay import download_video, fetch_ppt, timeline, write_json
from replay_library import (RUNTIME, read_json, course_folder, roots, writable,
                            video_complete, lesson_stem, subtitle_text, ordered_lectures, catalog)


def credentials():
    values = []
    for name in ("FUDAN_STUID", "FUDAN_UISPSW"):
        value = os.environ.get(name)
        if os.name == "nt":
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                    value = winreg.QueryValueEx(key, name)[0]
            except OSError:
                pass
        values.append(value)
    if not all(values):
        raise RuntimeError("请先设置 FUDAN_STUID 和 FUDAN_UISPSW")
    return values


def save_credentials(account, password):
    import winreg
    import ctypes
    if not account or not password:
        raise ValueError("账号和密码不能为空")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        for name, value in (("FUDAN_STUID", account), ("FUDAN_UISPSW", password)):
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            os.environ[name] = value
    result = ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(65535, 26, 0, "Environment", 2, 1000, ctypes.byref(result))


def login():
    from src.api.webvpn import WebVPNSession
    from src.api.icourse import ICourseClient
    account, password = credentials()
    for attempt in range(10):
        vpn = WebVPNSession()
        vpn.session.trust_env = False
        try:
            vpn.login(account, password)
            vpn.authenticate_icourse(account, password)
            client = ICourseClient(vpn)
            if not client.check_alive():
                raise RuntimeError("登录会话验证失败")
            return client
        except Exception:
            vpn.session.close()
            if attempt == 9:
                raise RuntimeError("复旦登录失败，请检查账号或网络") from None
            time.sleep(3)


def cloud_database(config):
    import requests
    from src.data.crypto_box import derive_new_password
    from src.data.sharder import load_index, reassemble_database
    repo = config["repository"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("GitHub 仓库名无效")
    with tempfile.TemporaryDirectory(dir=RUNTIME) as td:
        temp = Path(td)
        response = requests.get(f"https://api.github.com/repos/{repo}/commits/data", timeout=30)
        response.raise_for_status()
        sha = response.json()["sha"]
        cache = RUNTIME/"cloud.db"
        if cache.exists() and read_json(RUNTIME/"cloud-version.json", {}).get("sha") == sha:
            return cache
        response = requests.get(f"https://codeload.github.com/{repo}/zip/{sha}", timeout=120)
        response.raise_for_status()
        import io
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for member in z.infolist():
                parts = Path(member.filename).parts
                if member.is_dir() or len(parts) < 3 or parts[1] != "data":
                    continue
                relative = Path(*parts[2:])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("非法云端路径")
                dest = temp/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(member))
        account, password = credentials()
        key = derive_new_password(account, password)
        index = load_index(str(temp/"icourse-index.enc"), key)
        result = temp/"cloud.db"
        reassemble_database(index, str(temp/"shards"), str(result), key)
        with closing(sqlite3.connect(result)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("云端数据库不完整")
        result.replace(cache)
        write_json(RUNTIME/"cloud-version.json", {"sha": sha})
        return cache


def sync_subtitles(config):
    dbpath = cloud_database(config)
    count = 0
    with closing(sqlite3.connect(dbpath)) as db:
        cols = {r[1] for r in db.execute("PRAGMA table_info(lectures)")}
        if "transcript_segments" not in cols:
            return 0
        for course in catalog(config):
            folder = roots(config)[course["root"]]/course["folder"]
            for lesson in course["lessons"]:
                row = db.execute("SELECT transcript_segments FROM lectures WHERE sub_id=?", (lesson.get("sub_id"),)).fetchone()
                if not row or not row[0]:
                    continue
                content = subtitle_text(json.loads(row[0]))
                dest = folder/(lesson["name"]+".vtt")
                if not dest.exists() or dest.read_text(encoding="utf-8") != content:
                    temp = dest.with_suffix(".vtt.tmp")
                    temp.write_text(content, encoding="utf-8"); temp.replace(dest)
                    count += 1
    return count


def download(config, only=None):
    client = login()
    errors = []
    try:
        for cid in config["courses"]:
            detail = client.get_course_detail(cid)
            listing = ordered_lectures(detail["lectures"])
            for number, lecture in enumerate(listing, 1):
                if not lecture.get("has_playback") or (only and str(lecture["sub_id"]) != only):
                    continue
                sid, stem = str(lecture["sub_id"]), lesson_stem(number)
                folder = None
                for root in roots(config):
                    if not root.exists():
                        continue
                    for candidate in root.glob("*/"+stem+".lesson.json"):
                        m = read_json(candidate, {})
                        if m.get("sub_id") == sid and m.get("course_id") == cid:
                            folder = candidate.parent
                            break
                    if folder:
                        break
                if folder is None:
                    # Download onto local disk first so SMB outages cannot interrupt the media stream.
                    target = Path(config["fallback"])
                    target.mkdir(parents=True, exist_ok=True)
                    folder = course_folder(target, detail["title"], cid)
                record = folder/(stem+".lesson.json")
                old = read_json(record, {})
                if old and old.get("sub_id") != sid:
                    errors.append(f"{stem}: 课次顺序变化，保留原文件")
                    continue
                write_json(record, {"course_id": cid, "sub_id": sid, "number": number,
                                    "date": lecture.get("date", ""), "title": lecture.get("sub_title", "")})
                video = folder/(stem+".mp4")
                try:
                    if not video_complete(video):
                        print(f"下载 {detail['title']} {stem}", flush=True)
                        check = client.vpn.get(client.base_url+"/courseapi/v3/portal-home-setting/get-sub-info",
                                               params={"course_id": cid, "sub_id": sid}, timeout=30)
                        check.raise_for_status()
                        if check.json().get("code") != 0:
                            raise RuntimeError("没有课次访问权限")
                        url = client.get_video_url(cid, sid)
                        if not url:
                            raise RuntimeError("视频未就绪")
                        download_video(client, url, video)
                    assets = folder/(stem+".assets")
                    if not (assets/"timeline.json").exists():
                        assets.mkdir(exist_ok=True)
                        pages = timeline(client.get_ppt_list(cid, sid))
                        for i, page in enumerate(pages):
                            target = assets/f"{i+1:05}.jpg"
                            if not target.exists():
                                temp = target.with_suffix(".part")
                                temp.write_bytes(fetch_ppt(client.vpn, page["url"])); temp.replace(target)
                            page["file"] = target.name
                            page.pop("url", None)
                        write_json(assets/"timeline.json", pages)
                except Exception as e:
                    errors.append(f"{stem}: {type(e).__name__}")
                    print(f"{stem} 暂未完成，保留文件供下次重试 ({type(e).__name__})", flush=True)
    finally:
        client.vpn.session.close()
    return errors
