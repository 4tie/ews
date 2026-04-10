import os
import re


PAIR_PATTERN = re.compile(r"^[A-Z0-9]+/[A-Z0-9]+$")
TIMEFRAME_PATTERN = re.compile(r"^\d+[mhdwM]$")


class ValidationService:
    def validate_path(self, path: str) -> bool:
        return os.path.exists(path)

    def validate_freqtrade_path(self, path: str) -> dict:
        if not os.path.isdir(path):
            return {"valid": False, "error": "Directory does not exist"}
        ft_bin = os.path.join(path, "freqtrade")
        if not os.path.isfile(ft_bin):
            return {"valid": False, "error": "freqtrade binary not found in directory"}
        return {"valid": True}

    def validate_pair(self, pair: str) -> bool:
        return bool(PAIR_PATTERN.match(pair.upper()))

    def validate_pairs(self, pairs: list[str]) -> dict:
        valid = [p.upper() for p in pairs if PAIR_PATTERN.match(p.upper())]
        invalid = [p for p in pairs if not PAIR_PATTERN.match(p.upper())]
        return {"valid": valid, "invalid": invalid}

    def validate_timeframe(self, tf: str) -> bool:
        return bool(TIMEFRAME_PATTERN.match(tf))

    def validate_timerange(self, timerange: str) -> dict:
        """Validate freqtrade timerange format: YYYYMMDD-YYYYMMDD"""
        parts = timerange.split("-")
        if len(parts) != 2:
            return {"valid": False, "error": "Expected format: YYYYMMDD-YYYYMMDD"}
        for part in parts:
            if part and not re.match(r"^\d{8}$", part):
                return {"valid": False, "error": f"Invalid date segment: {part}"}
        return {"valid": True}
