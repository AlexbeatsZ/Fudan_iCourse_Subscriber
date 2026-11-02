"""When a lecture that failed processing should be attempted again."""

from datetime import date, timedelta

MAX_ERRORS = 3
# Replays are often published a day or more after class. With four runs a day,
# three no_video attempts used to abandon a lecture within ~18 hours forever.
NO_VIDEO_RETRY_DAYS = 7


def no_video_cutoff(today: date | None = None) -> str:
    """Earliest lecture date (YYYY-MM-DD) whose missing video is still retried."""
    return ((today or date.today()) - timedelta(days=NO_VIDEO_RETRY_DAYS)).isoformat()


def may_retry(row: dict, today: date | None = None) -> bool:
    if (row.get("error_count") or 0) < MAX_ERRORS:
        return True
    return row.get("error_stage") == "no_video" and (row.get("date") or "") >= no_video_cutoff(today)
