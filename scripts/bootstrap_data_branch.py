"""Create an independent data branch with an editable course list on first run.

No school credentials or database files are needed.  Existing data branches
are deliberately left untouched (including historical database-only branches).
"""

import os
from pathlib import Path
import re
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.subscriptions import MANIFEST_PATH, manifest_bytes, parse_csv


def ensure_data_branch(repository, token, course_ids="", *, session=None):
    """Return True if we created data, False if it was already present."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("GITHUB_REPOSITORY is invalid")
    if not token:
        raise ValueError("GITHUB_TOKEN is required to initialize the data branch")

    api = f"https://api.github.com/repos/{repository}/git"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }
    client = session or requests.Session()
    ref_url = f"{api}/ref/heads/data"
    response = client.get(ref_url, headers=headers, timeout=30)
    if response.status_code == 200:
        return False
    if response.status_code != 404:
        response.raise_for_status()

    # A root commit keeps the public data branch independent of main.  Only
    # the subscription list is published; there is no empty database to decode.
    tree = client.post(
        f"{api}/trees", headers=headers, timeout=30,
        json={"tree": [{
            "path": MANIFEST_PATH,
            "mode": "100644", "type": "blob",
            "content": manifest_bytes(parse_csv(course_ids)).decode("utf-8"),
        }]},
    )
    tree.raise_for_status()
    commit = client.post(
        f"{api}/commits", headers=headers, timeout=30,
        json={
            "message": "chore: initialize course subscriptions",
            "tree": tree.json()["sha"],
            "parents": [],
        },
    )
    commit.raise_for_status()
    created = client.post(
        f"{api}/refs", headers=headers, timeout=30,
        json={"ref": "refs/heads/data", "sha": commit.json()["sha"]},
    )
    if created.status_code == 201:
        return True
    if created.status_code == 422:
        # Two Actions runs can race to create the same branch; only treat the
        # conflict as success after verifying a real data ref now exists.
        concurrent = client.get(ref_url, headers=headers, timeout=30)
        if concurrent.status_code == 200:
            return False
    created.raise_for_status()
    raise RuntimeError(f"Unexpected GitHub create-ref status: {created.status_code}")


def main():
    created = ensure_data_branch(
        os.environ["GITHUB_REPOSITORY"],
        os.environ.get("GITHUB_TOKEN", ""),
        os.environ.get("INITIAL_COURSE_IDS", ""),
    )
    if created:
        print("Created data branch with public data/subscriptions.json.")
    else:
        print("data branch already exists; leaving subscriptions and database intact.")


if __name__ == "__main__":
    main()
