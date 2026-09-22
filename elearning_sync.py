"""List/select courses and poll eLearning into a local archive."""
import argparse
import json
from pathlib import Path
import sys
from contextlib import closing

from elearning.client import Client
from elearning.sync import (DEFAULT, Sync, course_id, error_label, load_config, now,
                            open_db, run_lock, write_json)

BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "local-data" / "elearning"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="复旦 eLearning 增量归档")
    parser.add_argument("--config", type=Path, default=RUNTIME / "settings.json")
    sub = parser.add_subparsers(dest="command", required=True)
    courses_parser = sub.add_parser("courses", help="列出当前可选课程")
    courses_parser.add_argument("--all-terms", action="store_true")
    select = sub.add_parser("select", help="保存订阅的课程编号或链接")
    select.add_argument("ids", nargs="*")
    select.add_argument("--all", action="store_true")
    select.add_argument("--interactive", action="store_true")
    select.add_argument("--destination")
    select.add_argument("--times", nargs="+")
    sub.add_parser("sync", help="轮询一次，下载新增/更新文件并读取通知")
    archive = sub.add_parser("archive", help="一次性归档课程，不改变定时订阅")
    archive.add_argument("ids", nargs="+")
    sub.add_parser("status", help="显示配置和上次运行结果")
    events = sub.add_parser("events", help="查看尚未发送的通知事件")
    events.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    config = load_config(args.config)
    runtime = args.config.resolve().parent
    if args.command == "status":
        last = runtime / "last-run.json"
        print(json.dumps({"config": config, "last_run": json.loads(last.read_text(encoding="utf-8")) if last.exists() else None}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "events":
        with closing(open_db(runtime)) as db:
            for row in db.execute("SELECT payload FROM events WHERE delivered=0 ORDER BY rowid LIMIT ?", (args.limit,)):
                print(row[0])
        return 0
    with run_lock(runtime):
        client = Client()
        try:
            client.login()
            if args.command in {"courses", "select"}:
                courses = client.courses(all_terms=getattr(args, "all_terms", False))
                write_json(runtime / "courses.json", courses)
                for c in courses:
                    print(f"{c['id']}\t{c.get('name', '')}\t{(c.get('term') or {}).get('name', '')}")
                if args.command == "courses":
                    return 0
                ids = [str(c["id"]) for c in courses] if args.all else [course_id(x) for x in args.ids]
                if args.interactive:
                    print("当前订阅：" + ", ".join(config["courses"]))
                    raw = input("输入课程编号（空格/逗号分隔），all 为全部，留空保持：").strip()
                    ids = ([str(c["id"]) for c in courses] if raw.lower() == "all" else
                           [course_id(x) for x in raw.replace(",", " ").replace("，", " ").split()]) if raw else config["courses"]
                available = {str(c["id"]) for c in courses}
                if set(ids) - available:
                    raise ValueError("所选课程不在当前可访问课程列表中")
                config["courses"] = list(dict.fromkeys(ids))
                if args.destination:
                    config["destination"] = args.destination
                if args.times:
                    config["times"] = args.times
                # Validate before publishing the new configuration.
                if not Path(config["destination"]).is_absolute():
                    raise ValueError("destination 必须是绝对路径")
                import re
                if any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", x) for x in config["times"]):
                    raise ValueError("时间应为 HH:mm")
                write_json(args.config, config)
                print(f"已保存 {len(ids)} 门课程。配置：{args.config}")
                return 0
            if args.command == "archive":
                config = config | {"courses": [course_id(x) for x in args.ids],
                                   "messages": False, "announcements": False}
            if not config["courses"]:
                raise ValueError("请先运行 select --all 或 select 课程编号")
            if config["destination"].startswith("\\\\192.168.137.1\\"):
                from replay_library import ensure_network_share
                ensure_network_share()
            sync = Sync(client, config, runtime)
            try:
                result = sync.run()
            finally:
                sync.close()
            print(json.dumps(result, ensure_ascii=False))
            return 1 if result["errors"] else 0
        finally:
            client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        message = error_label(exc)
        print("任务未完成：" + message, file=sys.stderr)
        # Per-run status is written by Sync; fatal login failures remain in task log.
        raise SystemExit(1) from None
