"""Public subscription configuration stored beside the encrypted data shards.

``data/subscriptions.json`` on each repository's own ``data`` branch is the
source of truth. No GitHub Actions COURSE_IDS secret is involved.
"""
import base64
import json
import re
import sqlite3

import requests


MANIFEST_PATH = "data/subscriptions.json"


def normalize_course_ids(values):
    if not isinstance(values, list):
        raise ValueError("subscriptions.json: course_ids must be an array")
    result = []
    for item in values:
        value = str(item).strip()
        if not value.isdecimal():
            raise ValueError("subscriptions.json: course IDs must be numeric")
        if value not in result:
            result.append(value)
    return result


def parse_csv(value):
    if not value or not value.strip():
        return []
    return normalize_course_ids([x.strip() for x in value.split(",") if x.strip()])


def manifest_bytes(course_ids):
    content = {"course_ids": normalize_course_ids(course_ids)}
    return (json.dumps(content, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def parse_manifest(raw):
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("subscriptions.json is not valid JSON") from error
    if not isinstance(data, dict) or "course_ids" not in data:
        raise ValueError("subscriptions.json must contain a course_ids array")
    return normalize_course_ids(data["course_ids"])


def fetch_manifest(repository, token, *, get=requests.get):
    """Return (IDs, branch_exists). IDs is None when no manifest is present."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("GITHUB_REPOSITORY is invalid")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    ref = get(f"https://api.github.com/repos/{repository}/git/ref/heads/data",
              headers=headers, timeout=30)
    if ref.status_code == 404:
        return None, False
    ref.raise_for_status()
    response = get(
        f"https://api.github.com/repos/{repository}/contents/{MANIFEST_PATH}?ref=data",
        headers=headers, timeout=30,
    )
    if response.status_code == 404:
        return None, True
    response.raise_for_status()
    payload = response.json()
    if payload.get("encoding") != "base64":
        raise ValueError("subscriptions.json has an unsupported GitHub encoding")
    return parse_manifest(base64.b64decode(payload["content"])), True


def legacy_course_ids(database_path):
    """One-time migration from already-encrypted data-branch metadata."""
    with sqlite3.connect(database_path) as db:
        for key in ("subscribed_course_ids", "course_ids"):
            try:
                row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            except sqlite3.OperationalError:
                return None
            if row is not None:
                return parse_csv(row[0])
    return None
