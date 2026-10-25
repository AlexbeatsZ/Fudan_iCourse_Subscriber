"""Write a subscription manifest during initial database deployment/migration."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.subscriptions import manifest_bytes, parse_csv


def main():
    target = Path(sys.argv[1])
    if "SUBSCRIBED_COURSE_IDS" not in os.environ:
        print("No subscription source available; leaving manifest absent.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(manifest_bytes(parse_csv(os.environ["SUBSCRIBED_COURSE_IDS"])))


if __name__ == "__main__":
    main()
