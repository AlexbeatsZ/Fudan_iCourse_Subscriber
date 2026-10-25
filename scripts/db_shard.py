#!/usr/bin/env python3
"""Bidirectional DB shard CLI used by GitHub Actions workflows.

Usage:
    python scripts/db_shard.py shard      <db_path>    <output_dir>
    python scripts/db_shard.py reassemble <input_dir>  <db_path>
    python scripts/db_shard.py decode-legacy <encrypted_file> <db_path>

Uses DB_PASSWORD when set; otherwise derives the v2 key from STUID and
UISPSW. Old keys can be read during migration. The shard subcommands
operate on the layout produced by `src.sharder`:
    <dir>/icourse-index.enc
    <dir>/shards/shard-NNNN.db.gz.enc
"""

from __future__ import annotations

import os
import sys
import gzip

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.crypto_box import (decrypt, derive_new_password,
    derive_custom_password, is_gzip, is_sqlite, password_candidates)
from src.data.sharder import (
    INDEX_FILENAME,
    SHARDS_DIR,
    load_index,
    reassemble_database,
    shard_database,
)


def _password() -> str:
    db_password = os.environ.get("DB_PASSWORD", "")
    if db_password:
        return derive_custom_password(db_password)
    stuid = os.environ.get("STUID") or os.environ.get("StuId", "")
    uispsw = os.environ.get("UISPSW") or os.environ.get("UISPsw", "")
    if not stuid or not uispsw:
        print("error: set DB_PASSWORD or both STUID and UISPSW", file=sys.stderr)
        sys.exit(2)
    return derive_new_password(stuid, uispsw)


def _candidates(include_legacy=False):
    return password_candidates(
        stuid=os.environ.get("STUID") or os.environ.get("StuId", ""),
        uispsw=os.environ.get("UISPSW") or os.environ.get("UISPsw", ""),
        db_password=os.environ.get("DB_PASSWORD", ""),
        previous_db_password=os.environ.get("DB_PASSWORD_PREVIOUS", ""),
        dashscope=os.environ.get("DASHSCOPE_API_KEY", ""),
        smtp=os.environ.get("SMTP_PASSWORD", ""),
        include_legacy=include_legacy,
    )


def _report_key(label: str):
    preferred = "custom" if os.environ.get("DB_PASSWORD") else "v2"
    if label != preferred:
        print(f"Database read with {label} key; re-encryption required.")
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write("needs_rekey=true\n")


def _cmd_shard(db_path: str, output_dir: str):
    if not os.path.isfile(db_path):
        print(f"error: not a file: {db_path}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(output_dir, exist_ok=True)
    index = shard_database(db_path, output_dir, _password())
    n = len(index["shards"])
    print(f"sharded → {n} shard(s) under {output_dir}/")


def _cmd_reassemble(input_dir: str, db_path: str):
    index_path = os.path.join(input_dir, INDEX_FILENAME)
    if not os.path.isfile(index_path):
        print(f"error: index not found at {index_path}", file=sys.stderr)
        sys.exit(1)
    shards_dir = os.path.join(input_dir, SHARDS_DIR)
    for label, pw, _ in _candidates():
        try:
            index = load_index(index_path, pw)
            reassemble_database(index, shards_dir, db_path, pw)
            break
        except (ValueError, UnicodeDecodeError):
            continue
    else:
        raise ValueError("Cannot decrypt database shards. Check DB_PASSWORD and old credentials.")
    _report_key(label)
    n = len(index["shards"])
    print(f"reassembled {n} shard(s) → {db_path}")


def _cmd_decode_legacy(input_path: str, db_path: str):
    with open(input_path, "rb") as f:
        blob = f.read()
    for label, pw, iterations in _candidates(include_legacy=True):
        try:
            plaintext = decrypt(blob, pw, iterations)
            if is_gzip(plaintext):
                plaintext = gzip.decompress(plaintext)
            if not is_sqlite(plaintext):
                continue
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            with open(db_path, "wb") as f:
                f.write(plaintext)
            _report_key(label)
            print(f"Decoded legacy database → {db_path}")
            return
        except (ValueError, OSError):
            continue
    raise ValueError("Cannot decrypt legacy database. Check DB_PASSWORD and old credentials.")


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    cmd, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
    if cmd == "shard":
        _cmd_shard(a, b)
    elif cmd == "reassemble":
        _cmd_reassemble(a, b)
    elif cmd == "decode-legacy":
        _cmd_decode_legacy(a, b)
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
