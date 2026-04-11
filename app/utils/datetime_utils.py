from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def timestamp_slug() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


def parse_timerange(timerange: str) -> tuple[str, str]:
    """Parse a freqtrade-style timerange '20230101-20240101' into (start, end)."""
    parts = timerange.split("-")
    if len(parts) == 2:
        return parts[0], parts[1]
    return timerange, ""


def format_duration_seconds(seconds: float) -> str:
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h {mins}m {secs}s"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"
