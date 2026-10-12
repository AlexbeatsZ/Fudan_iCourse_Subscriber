"""Read-only OMEN file manifests. Never emits credentials or campus session state."""
import argparse
import json
from pathlib import Path

ROOTS = {"videos": Path("D:/Videos"), "elearning": Path("D:/Documents/Elearning")}
TRANSIENT = (".part", ".transfer", ".tmp", ".elearning-transfer")


def allowed(path):
    return path.is_file() and not path.is_symlink() and not path.name.endswith(TRANSIENT) and path.name not in {"desktop.ini", ".DS_Store"}


def safe_path(root, relative):
    from pathlib import PurePosixPath
    rel = PurePosixPath(relative)
    if rel.is_absolute() or any(p in {".", ".."} or "\\" in p or ":" in p for p in rel.parts):
        raise ValueError("Invalid relative path")
    result = root.joinpath(*rel.parts)
    if not result.resolve().is_relative_to(root.resolve()) or result.is_symlink():
        raise ValueError("Path outside archive")
    return result


def record(root, path):
    stat = path.stat()
    return {"path": path.relative_to(root).as_posix(), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def collect(kind, root):
    paths = []
    if kind == "elearning":
        paths = [p for p in root.rglob("*") if allowed(p)]
    else:
        for folder in root.iterdir():
            if not folder.is_dir() or folder.is_symlink() or not (folder / "course.json").is_file():
                continue
            info = json.loads((folder / "course.json").read_text(encoding="utf-8-sig"))
            if not info.get("course_id"):
                continue
            videos = []
            for video in folder.glob("*.mp4"):
                receipt = video.with_suffix(".mp4.json")
                try:
                    saved = json.loads(receipt.read_text(encoding="utf-8-sig"))
                    if allowed(video) and saved.get("complete") and saved.get("total") == video.stat().st_size:
                        videos.append(video)
                except (ValueError, OSError):
                    continue
            if not videos:
                continue
            paths.append(folder / "course.json")
            for video in videos:
                paths += [p for p in folder.glob(video.stem + ".*") if allowed(p)]
                assets = video.with_suffix(".assets")
                if assets.is_dir() and not assets.is_symlink():
                    paths += [p for p in assets.rglob("*") if allowed(p)]
    rows = [record(root, p) for p in paths]
    # Every sidecar is available before a completed video appears in the player.
    return sorted(rows, key=lambda r: (r["path"].split("/")[0], r["path"].endswith(".mp4"), r["path"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=ROOTS)
    parser.add_argument("--path", help="Stat one file for post-transfer version verification")
    args = parser.parse_args()
    root = ROOTS[args.kind]
    if args.path:
        result = record(root, safe_path(root, args.path))
    else:
        result = {"root": root.as_posix(), "files": collect(args.kind, root)}
        if args.kind == "elearning":
            result["directories"] = [p.relative_to(root).as_posix() for p in root.rglob("*")
                                     if p.is_dir() and not p.is_symlink()]
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
