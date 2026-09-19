from contextlib import closing
"""Cheap hourly probe; load no OCR or speech models when nothing needs work."""
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.downloader import login, cloud_database
from replay_library import settings, ordered_lectures


def main():
    config = settings()
    config["courses"] = [v.strip() for v in os.environ.get("COURSE_IDS", "").split(",") if v.strip()]
    if not config["courses"]:
        needed = False
    else:
        client = login()
        try:
            # A missing data branch is the first-run case. Other errors must fail loudly.
            import requests
            try:
                dbpath = cloud_database(config)
            except requests.HTTPError as e:
                if e.response.status_code != 404:
                    raise
                dbpath = None
            needed = dbpath is None
            if dbpath:
                with closing(sqlite3.connect(dbpath)) as db:
                    db.row_factory = sqlite3.Row
                    for cid in config["courses"]:
                        for lecture in ordered_lectures(client.get_course_detail(cid)["lectures"]):
                            if not lecture.get("has_playback"):
                                continue
                            row = db.execute("SELECT * FROM lectures WHERE sub_id=?", (str(lecture["sub_id"]),)).fetchone()
                            row = dict(row) if row else {}
                            if (row.get("error_count") or 0) < 3 and (not row.get("processed_at") or not row.get("transcript_segments")):
                                needed = True
        finally:
            client.vpn.session.close()
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write("needed="+str(needed).lower()+"\n")
    print("New processing required: "+str(needed))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Replay check failed: "+type(e).__name__)
        sys.exit(1)
