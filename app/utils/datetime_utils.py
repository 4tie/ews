"""
datetime_utils.py — Datetime utilities for ISO formatting, timestamps, and timerange parsing.
"""

from datetime import datetime, timezone
import time


def now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def timestamp_slug() -> str:
    """Generate a timestamp-based slug (milliseconds since epoch)."""
    return str(int(time.time() * 1000))


def parse_timerange(timerange_str: str) -> tuple[str | None, str | None]:
    """
    Parse freqtrade timerange format: YYYYMMDD-YYYYMMDD or YYYYMMDD- or -YYYYMMDD.
    
    Returns: (start_token, end_token) where each is YYYYMMDD or None
    
    Examples:
        "20250701-20260411" -> ("20250701", "20260411")
        "20250701-" -> ("20250701", None)
        "-20260411" -> (None, "20260411")
        "20250701" -> ("20250701", None)
    """
    if not timerange_str or not isinstance(timerange_str, str):
        return None, None
    
    timerange_str = timerange_str.strip()
    
    if "-" not in timerange_str:
        # Single date, treat as start
        if len(timerange_str) == 8 and timerange_str.isdigit():
            return timerange_str, None
        return None, None
    
    parts = timerange_str.split("-", 1)
    start = parts[0].strip() if parts[0].strip() else None
    end = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    
    # Validate format
    if start and (len(start) != 8 or not start.isdigit()):
        start = None
    if end and (len(end) != 8 or not end.isdigit()):
        end = None
    
    return start, end
