"""Cheap scheduled probe; load no OCR or speech models when nothing needs work."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import urlsplit

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.downloader import login, cloud_database
from replay_library import settings, ordered_lectures


def error_summary(error):
    """Keep status/host diagnostics without leaking CAS tickets or signed URLs."""
    response = getattr(error, "response", None)
    if response is not None:
        host = urlsplit(response.url or "").hostname or "unknown host"
        return f"{type(error).__name__} (HTTP {response.status_code}, {host})"
    # Explicit, controlled messages are safe; arbitrary network exception text
    # may include authenticated URLs and must never be printed.
    message = str(error)
    if message.startswith((
        "COURSE_IDS ", "GITHUB_REPOSITORY ", "STUID / UISPSW ",
        "云端数据库解密失败", "课程 ",
    )):
        return message
    return type(error).__name__


def transient_error(error):
    if isinstance(error, (requests.Timeout, requests.ConnectionError,
                          requests.exceptions.JSONDecodeError)):
        return True
    if isinstance(error, requests.HTTPError) and error.response is not None:
        response = error.response
        return response.status_code in (408, 429, 500, 502, 503, 504) or (
            response.status_code == 403 and (
                response.headers.get("X-RateLimit-Remaining") == "0"
                or "Retry-After" in response.headers))
    return False


def probe(config):
    if not config["courses"]:
        return False
    else:
        client = login()
        try:
            # A missing data branch is the first-run case. Other errors must fail loudly.
            print("Checking cloud database", flush=True)
            try:
                dbpath = cloud_database(config)
            except requests.HTTPError as e:
                response = e.response
                source = urlsplit(response.url or "") if response is not None else None
                if (response is None or response.status_code != 404
                        or source.hostname != "api.github.com"
                        or source.path != f"/repos/{config['repository']}/git/ref/heads/data"):
                    raise
                dbpath = None
            needed = dbpath is None or config.get("_needs_rekey", False)
            if dbpath:
                with closing(sqlite3.connect(dbpath)) as db:
                    db.row_factory = sqlite3.Row
                    for cid in config["courses"]:
                        print(f"Checking course {cid}", flush=True)
                        try:
                            lectures = client.get_course_detail(cid)["lectures"]
                        except Exception as error:
                            raise RuntimeError(
                                f"课程 {cid} 无法读取：请确认 COURSE_IDS 和课程访问权限"
                            ) from error
                        for lecture in ordered_lectures(lectures):
                            if not lecture.get("has_playback"):
                                continue
                            row = db.execute("SELECT * FROM lectures WHERE sub_id=?", (str(lecture["sub_id"]),)).fetchone()
                            row = dict(row) if row else {}
                            if (row.get("error_count") or 0) < 3 and (not row.get("processed_at") or not row.get("transcript_segments")):
                                needed = True
        finally:
            client.vpn.session.close()
    return needed


def main():
    config = settings()
    # Also honour an explicit repository environment outside Actions.
    if os.environ.get("GITHUB_REPOSITORY"):
        config["repository"] = os.environ["GITHUB_REPOSITORY"]
    env_courses = [v.strip() for v in os.environ.get("COURSE_IDS", "").split(",") if v.strip()]
    if not env_courses:
        print("No subscriptions configured. Edit data/subscriptions.json on the data branch to start monitoring.")
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write("needed=false\n")
        return
    if not all(v.isdecimal() for v in env_courses):
        raise ValueError("COURSE_IDS must contain comma-separated numeric course IDs")
    if os.environ.get("GITHUB_ACTIONS") == "true" and not (
        os.environ.get("FUDAN_STUID") and os.environ.get("FUDAN_UISPSW")
    ):
        raise RuntimeError("STUID / UISPSW Secrets 未配置")
    config["courses"] = env_courses
    for attempt in range(1, 4):
        try:
            needed = probe(config)
            if os.environ.get("SUBSCRIPTIONS_NEEDS_MIGRATION") == "1":
                needed = True
            break
        except requests.RequestException as error:
            if attempt == 3 or not transient_error(error):
                raise
            print(f"Replay check attempt {attempt}/3 failed: {error_summary(error)}; retrying",
                  flush=True)
            time.sleep(5 * attempt)
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write("needed="+str(needed).lower()+"\n")
    print("New processing required: "+str(needed))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Replay check failed: "+error_summary(e))
        sys.exit(1)
