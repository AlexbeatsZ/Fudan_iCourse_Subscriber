"""Idempotently initialize *all* cloud data files before normal work.

Only a main branch is required at installation time.  The initial run creates
an independent data branch with public subscriptions.json and an encrypted,
schema-ready SQLite index and shards.  Any run that creates missing files
stops after initialization; the following run can process courses normally.

Existing encrypted data is never reset, replaced or force-pushed.
"""

import base64
import os
from pathlib import Path
import re
import sys
import tempfile

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.crypto_box import derive_custom_password, derive_new_password
from src.data.database import Database
from src.data.sharder import shard_database
from src.data.subscriptions import (MANIFEST_PATH, legacy_course_ids,
                                    manifest_bytes, parse_csv)


def _new_database_files(course_ids, *, stuid, uispsw, db_password):
    """Return encrypted files ready for Git blobs, leaving no plaintext behind."""
    if db_password:
        password = derive_custom_password(db_password)
    elif stuid and uispsw:
        password = derive_new_password(stuid, uispsw)
    else:
        raise ValueError("STUID / UISPSW or DB_PASSWORD required to initialize encrypted data")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db = Database(str(root / "initial.db"))
        db.write_meta("subscribed_course_ids", ",".join(course_ids))
        db.conn.close()
        output = root / "sharded"
        shard_database(str(root / "initial.db"), str(output), password)
        return {
            "data/" + path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*") if path.is_file()
        }


def _response_json(response):
    response.raise_for_status()
    return response.json()


def _read_branch(client, api, headers):
    ref = client.get(f"{api}/ref/heads/data", headers=headers, timeout=30)
    if ref.status_code == 404:
        return None, None, set()
    parent = _response_json(ref)["object"]["sha"]
    commit = _response_json(client.get(
        f"{api}/commits/{parent}", headers=headers, timeout=30))
    tree_sha = commit["tree"]["sha"]
    tree = _response_json(client.get(
        f"{api}/trees/{tree_sha}?recursive=1", headers=headers, timeout=30))
    if tree.get("truncated"):
        raise RuntimeError("data branch tree is truncated; refusing to initialize")
    return parent, tree_sha, {entry["path"] for entry in tree["tree"] if entry["type"] == "blob"}


def _migrate_subscriptions(repository):
    """Preserve legacy subscriptions when an old DB has no public manifest."""
    from desktop.downloader import cloud_database
    # cloud_database reads credentials from these Actions environment names.
    dbpath = cloud_database({"repository": repository})
    return legacy_course_ids(dbpath) if dbpath is not None else []


def ensure_data_branch(repository, token, course_ids="", *, session=None,
                       stuid="", uispsw="", db_password=""):
    """Return True if files were initialized, False if data was already ready."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("GITHUB_REPOSITORY is invalid")
    if not token:
        raise ValueError("GITHUB_TOKEN is required to initialize data")
    explicit = parse_csv(course_ids)
    api = f"https://api.github.com/repos/{repository}/git"
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    client = session or requests.Session()

    saw_missing_files = False
    for attempt in range(3):
        parent, base_tree, files = _read_branch(client, api, headers)
        has_index = "data/icourse-index.enc" in files
        has_legacy = bool(files & {"data/icourse.db.gz.enc", "data/icourse.db.enc"})
        has_db = has_index or has_legacy
        has_manifest = MANIFEST_PATH in files
        if has_db and has_manifest:
            return saw_missing_files

        saw_missing_files = True

        if has_index and not any(path.startswith("data/shards/") and path.endswith(".enc")
                                 for path in files):
            raise FileNotFoundError("data has an encrypted index but no shards; refusing to overwrite")

        if not has_db and any(path.startswith("data/shards/") and path.endswith(".enc")
                              for path in files):
            raise FileNotFoundError("data has encrypted shards but no index; refusing to overwrite")

        ids = explicit
        if not has_manifest and has_db:
            ids = _migrate_subscriptions(repository)

        entries = []
        if not has_manifest:
            entries.append({"path": MANIFEST_PATH, "mode": "100644", "type": "blob",
                            "content": manifest_bytes(ids).decode("utf-8")})

        if not has_db:
            # When subscriptions.json already exists, don't replace its user
            # choices with a one-off Single Run input.  Empty DB metadata is
            # harmless; normal processing reads the manifest separately.
            for path, content in _new_database_files(
                    ids if not has_manifest else [],
                    stuid=stuid, uispsw=uispsw, db_password=db_password).items():
                blob = _response_json(client.post(
                    f"{api}/blobs", headers=headers, timeout=30,
                    json={"content": base64.b64encode(content).decode("ascii"),
                          "encoding": "base64"}))
                entries.append({"path": path, "mode": "100644", "type": "blob",
                                "sha": blob["sha"]})

        tree_payload = {"tree": entries}
        if base_tree is not None:
            tree_payload["base_tree"] = base_tree
        tree = _response_json(client.post(
            f"{api}/trees", headers=headers, timeout=30, json=tree_payload))
        commit = _response_json(client.post(
            f"{api}/commits", headers=headers, timeout=30,
            json={"message": "chore: initialize missing data files",
                  "tree": tree["sha"], "parents": [parent] if parent else []}))

        if parent:
            published = client.patch(
                f"{api}/refs/heads/data", headers=headers, timeout=30,
                json={"sha": commit["sha"], "force": False})
            if published.status_code == 200:
                return True
        else:
            published = client.post(
                f"{api}/refs", headers=headers, timeout=30,
                json={"ref": "refs/heads/data", "sha": commit["sha"]})
            if published.status_code == 201:
                return True
        # Another workflow/frontend edit may have advanced data.  Retry from
        # the latest ref; GitHub rejects non-fast-forward updates by default.
        if published.status_code not in (409, 422) or attempt == 2:
            published.raise_for_status()
            raise RuntimeError(f"Unexpected data update status: {published.status_code}")
    raise RuntimeError("Unable to initialize data after concurrent updates")


def main():
    initialized = ensure_data_branch(
        os.environ["GITHUB_REPOSITORY"],
        os.environ.get("GITHUB_TOKEN", ""),
        os.environ.get("INITIAL_COURSE_IDS", ""),
        stuid=os.environ.get("STUID") or os.environ.get("FUDAN_STUID", ""),
        uispsw=os.environ.get("UISPSW") or os.environ.get("FUDAN_UISPSW", ""),
        db_password=os.environ.get("DB_PASSWORD", ""),
    )
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"initialized={str(initialized).lower()}\n")
    if initialized:
        print("Initialized missing data files. This run ends after setup; run again to process courses.")
    else:
        print("All data files already exist; continuing normal workflow.")


if __name__ == "__main__":
    main()
