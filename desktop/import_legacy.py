"""Copy an existing verified local_replay library; leave source intact for acceptance."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.downloader import login
from replay_library import (settings, course_folder, ordered_lectures, lesson_stem,
                            copy_verified, write_json, read_json, video_complete, queue_lock)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    cfg = settings()
    target_root = Path(cfg["fallback"])
    target_root.mkdir(parents=True, exist_ok=True)
    client = login()
    import tempfile, shutil
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = Path(tf.name)
    try:
        shutil.copyfile(args.source/"library.sqlite3", temp_db)
        with queue_lock(), closing(sqlite3.connect(temp_db)) as db:
            for cid, title in db.execute("SELECT id,title FROM courses"):
                detail = client.get_course_detail(cid)
                lectures = ordered_lectures(detail["lectures"])
                for number, lecture in enumerate(lectures, 1):
                    sid = str(lecture["sub_id"])
                    source = args.source/cid/sid
                    if not video_complete(source/"video.mp4"):
                        continue
                    folder = course_folder(target_root, title, cid)
                    stem = lesson_stem(number)
                    copy_verified(source/"video.mp4", folder/(stem+".mp4"))
                    copy_verified(source/"video.mp4.json", folder/(stem+".mp4.json"))
                    write_json(folder/(stem+".lesson.json"), {"course_id":cid,"sub_id":sid,"number":number,"date":lecture.get("date",""),"title":lecture.get("sub_title","")})
                    pages = read_json(source/"timeline.json", [])
                    assets = folder/(stem+".assets")
                    assets.mkdir(exist_ok=True)
                    for page in pages:
                        relative = Path(page["file"])
                        if relative.is_absolute() or ".." in relative.parts:
                            raise ValueError("Invalid old slide path")
                        copy_verified(source/relative, assets/relative.name)
                        page["file"] = relative.name
                    write_json(assets/"timeline.json", pages)
                    print(f"Imported {cid}/{sid}: {stem}", flush=True)
    finally:
        temp_db.unlink(missing_ok=True)
        client.vpn.session.close()


if __name__ == "__main__":
    main()
