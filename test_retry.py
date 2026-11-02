from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import check_new_replays as check
from src.data.database import Database
from src.data.retry import NO_VIDEO_RETRY_DAYS, may_retry


def day(offset):
    return (date.today() - timedelta(days=offset)).isoformat()


class NoVideoRetryTest(unittest.TestCase):
    def test_missing_replay_is_retried_for_a_week_then_skipped(self):
        today = date(2026, 11, 2)
        row = {"error_stage": "no_video", "error_count": 3}
        self.assertTrue(may_retry({**row, "date": "2026-10-27"}, today))
        self.assertTrue(may_retry({**row, "error_count": 12, "date": "2026-10-26"}, today))
        self.assertFalse(may_retry({**row, "date": "2026-10-25"}, today))
        self.assertFalse(may_retry({**row, "date": None}, today))

    def test_other_failures_keep_the_three_attempt_limit(self):
        today = date(2026, 11, 2)
        self.assertTrue(may_retry({}, today))
        self.assertTrue(may_retry({"error_stage": "transcribe", "error_count": 2, "date": "2026-11-01"}, today))
        self.assertFalse(may_retry({"error_stage": "transcribe", "error_count": 3, "date": "2026-11-01"}, today))

    def test_unprocessed_lectures_include_recent_missing_replays_only(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(str(Path(directory) / "lectures.db"))
            try:
                for sub_id, offset, stage in (("recent", 5, "no_video"), ("old", NO_VIDEO_RETRY_DAYS + 1, "no_video"),
                                              ("broken", 1, "transcribe")):
                    db.insert_lecture(sub_id, "1", sub_id, day(offset))
                    for _ in range(3):
                        db.update_error(sub_id, stage, "failed")
                self.assertEqual([row["sub_id"] for row in db.get_unprocessed_lectures("1")], ["recent"])
            finally:
                db.conn.close()

    def test_probe_runs_again_while_a_recent_replay_is_missing(self):
        for offset, needed in ((2, True), (NO_VIDEO_RETRY_DAYS + 1, False)):
            client = Mock()
            client.get_course_detail.return_value = {"lectures": [{"sub_id": "9", "has_playback": True}]}
            with tempfile.TemporaryDirectory() as directory:
                dbpath = Path(directory) / "cloud.db"
                with closing(sqlite3.connect(dbpath)) as db, db:
                    db.execute("CREATE TABLE lectures(sub_id TEXT, date TEXT, processed_at TEXT, "
                               "transcript_segments TEXT, error_count INTEGER, error_stage TEXT)")
                    db.execute("INSERT INTO lectures VALUES('9',?,NULL,NULL,3,'no_video')", (day(offset),))
                with (patch.object(check, "login", return_value=client),
                      patch.object(check, "cloud_database", return_value=dbpath),
                      patch.object(check, "ordered_lectures", side_effect=lambda lectures: lectures)):
                    self.assertEqual(check.probe({"repository": "owner/repo", "courses": ["1"]}), needed)


if __name__ == "__main__":
    unittest.main()
