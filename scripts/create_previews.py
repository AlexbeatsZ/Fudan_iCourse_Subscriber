"""Cache real video stills beside the existing lecture assets; no media rewrites."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def create_previews(root, executable=None):
    executable = executable or shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to create video stills")
    created = 0
    for folder in sorted(Path(root).iterdir()):
        if not folder.is_dir() or not (folder / "course.json").is_file():
            continue
        for video in sorted(folder.glob("*.mp4")):
            assets = video.with_suffix(".assets")
            output = assets / "preview.jpg"
            if output.is_file():
                continue
            assets.mkdir(exist_ok=True)
            pending = assets / "preview.tmp.jpg"
            try:
                for timestamp in ("90", "0"):
                    result = subprocess.run(
                        [executable, "-hide_banner", "-loglevel", "error", "-nostdin",
                         "-ss", timestamp, "-i", str(video), "-frames:v", "1",
                         "-vf", "scale=640:-2", "-q:v", "4", "-y", str(pending)],
                        capture_output=True, timeout=45,
                    )
                    if result.returncode == 0 and pending.is_file() and pending.stat().st_size:
                        pending.replace(output)
                        created += 1
                        break
                else:
                    print("Preview unavailable:", folder.name, video.name, file=sys.stderr)
            finally:
                pending.unlink(missing_ok=True)
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print("Created video stills:", create_previews(args.root))
