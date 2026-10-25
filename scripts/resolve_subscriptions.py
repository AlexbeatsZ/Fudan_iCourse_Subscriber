"""Resolve data-branch subscriptions for scheduled and one-off Actions jobs.

Outputs COURSE_IDS (an ephemeral process input), SUBSCRIBED_COURSE_IDS (the
permanent set for sharding), and SUBSCRIPTIONS_NEEDS_MIGRATION to GITHUB_ENV.
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.subscriptions import fetch_manifest, legacy_course_ids, parse_csv


def resolve(repository, token, mode, input_ids=""):
    saved, branch_exists = fetch_manifest(repository, token)
    missing_manifest = saved is None
    if missing_manifest and branch_exists:
        # Existing installations only have this information in their
        # encrypted DB. Migrate it without reading the old COURSE_IDS secret.
        from desktop.downloader import cloud_database
        dbpath = cloud_database({"repository": repository})
        saved = legacy_course_ids(dbpath)
    explicit = parse_csv(input_ids)
    if mode == "single":
        effective = explicit if input_ids.strip() else (saved or [])
        if saved is None:
            saved = effective  # First one-off run bootstraps persistent subscriptions.
    else:
        effective = saved or []
    return effective, (saved or []), missing_manifest and saved is not None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "single"], required=True)
    args = parser.parse_args()
    repository = os.environ["GITHUB_REPOSITORY"]
    ids, subscribed, needs_migration = resolve(
        repository, os.environ.get("GITHUB_TOKEN", ""), args.mode,
        os.environ.get("SINGLE_RUN_COURSE_IDS", ""),
    )
    target = os.environ["GITHUB_ENV"]
    with open(target, "a", encoding="utf-8") as output:
        output.write("COURSE_IDS=" + ",".join(ids) + "\n")
        output.write("SUBSCRIBED_COURSE_IDS=" + ",".join(subscribed) + "\n")
        output.write("SUBSCRIPTIONS_NEEDS_MIGRATION=" + ("1" if needs_migration else "0") + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("has_courses=" + ("true" if ids else "false") + "\n")
    print(f"Using {len(ids)} course(s); persisted {len(subscribed)} subscription(s)."
          + (" Subscription manifest migration pending." if needs_migration else ""))


if __name__ == "__main__":
    main()
