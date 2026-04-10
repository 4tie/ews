import os
import re
from datetime import datetime

from app.utils.freqtrade_resolver import resolve_freqtrade_executable


PAIR_PATTERN = re.compile(r"^[A-Z0-9]+/[A-Z0-9]+$")
TIMEFRAME_PATTERN = re.compile(r"^\d+[mhdwM]$")


class ValidationService:
    def validate_path(self, path: str) -> bool:
        return os.path.exists(path)

    def validate_freqtrade_path(self, path: str) -> dict:
        try:
            resolved = resolve_freqtrade_executable(path)
        except ValueError as exc:
            return {"valid": False, "error": str(exc)}
        return {"valid": True, "resolved_path": resolved}

    def validate_pair(self, pair: str) -> bool:
        return bool(PAIR_PATTERN.match(pair.upper()))

    def validate_pairs(self, pairs: list[str]) -> dict:
        valid = [p.upper() for p in pairs if PAIR_PATTERN.match(p.upper())]
        invalid = [p for p in pairs if not PAIR_PATTERN.match(p.upper())]
        return {"valid": valid, "invalid": invalid}

    def validate_timeframe(self, tf: str) -> bool:
        return bool(TIMEFRAME_PATTERN.match(tf))

    def validate_timerange(self, timerange: str) -> dict:
        """Validate freqtrade timerange format: YYYYMMDD-YYYYMMDD."""
        parts = timerange.split("-")
        if len(parts) != 2:
            return {"valid": False, "error": "Expected format: YYYYMMDD-YYYYMMDD"}

        parsed: list[datetime | None] = []
        for part in parts:
            if not part:
                parsed.append(None)
                continue
            if not re.match(r"^\d{8}$", part):
                return {"valid": False, "error": f"Invalid date segment: {part}"}
            try:
                parsed.append(datetime.strptime(part, "%Y%m%d"))
            except ValueError:
                return {"valid": False, "error": f"Invalid calendar date: {part}"}

        start_dt, end_dt = parsed
        if start_dt and end_dt and start_dt > end_dt:
            return {"valid": False, "error": "Timerange start must be before or equal to the end date"}

        return {
            "valid": True,
            "start": parts[0] or None,
            "end": parts[1] or None,
        }
