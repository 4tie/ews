"""
validation_service.py — Validation service for timeframe, pair, and timerange validation.
"""

import re
from app.utils.datetime_utils import parse_timerange


class ValidationService:
    """Service for validating backtest parameters."""
    
    # Valid freqtrade timeframes
    VALID_TIMEFRAMES = {
        "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "6h", "8h", "12h",
        "1d", "3d", "1w", "1M"
    }
    
    def validate_timeframe(self, timeframe: str) -> bool:
        """
        Validate if timeframe is supported by freqtrade.
        
        Args:
            timeframe: Timeframe string (e.g., "5m", "1h")
        
        Returns:
            True if valid, False otherwise
        """
        if not timeframe or not isinstance(timeframe, str):
            return False
        return timeframe.strip() in self.VALID_TIMEFRAMES
    
    def validate_pair(self, pair: str) -> bool:
        """
        Validate pair format (BASE/QUOTE).
        
        Args:
            pair: Pair string (e.g., "BTC/USDT")
        
        Returns:
            True if valid format, False otherwise
        """
        if not pair or not isinstance(pair, str):
            return False
        
        pair = pair.strip()
        
        # Must contain exactly one slash
        if pair.count("/") != 1:
            return False
        
        base, quote = pair.split("/")
        
        # Both parts must be non-empty and alphanumeric
        if not base or not quote:
            return False
        
        if not re.match(r"^[A-Z0-9]+$", base) or not re.match(r"^[A-Z0-9]+$", quote):
            return False
        
        return True
    
    def validate_timerange(self, timerange: str) -> dict:
        """
        Validate timerange format.
        
        Args:
            timerange: Timerange string (e.g., "20250701-20260411")
        
        Returns:
            Dict with 'valid' bool and optional 'error' message
        """
        if not timerange or not isinstance(timerange, str):
            return {"valid": False, "error": "Timerange must be a non-empty string"}
        
        start, end = parse_timerange(timerange)
        
        if start is None and end is None:
            return {"valid": False, "error": "Invalid timerange format. Use YYYYMMDD-YYYYMMDD"}
        
        # Validate date format
        if start:
            try:
                int(start)
                if len(start) != 8:
                    return {"valid": False, "error": f"Start date must be YYYYMMDD, got {start}"}
            except ValueError:
                return {"valid": False, "error": f"Start date must be numeric, got {start}"}
        
        if end:
            try:
                int(end)
                if len(end) != 8:
                    return {"valid": False, "error": f"End date must be YYYYMMDD, got {end}"}
            except ValueError:
                return {"valid": False, "error": f"End date must be numeric, got {end}"}
        
        # Validate date order if both present
        if start and end:
            if int(start) > int(end):
                return {"valid": False, "error": f"Start date {start} is after end date {end}"}
        
        return {"valid": True}
    
    def validate_pairs(self, pairs: list) -> dict:
        """
        Validate a list of pairs.
        
        Args:
            pairs: List of pair strings
        
        Returns:
            Dict with 'valid' bool, 'invalid_pairs' list, and optional 'error' message
        """
        if not pairs or not isinstance(pairs, list):
            return {"valid": False, "invalid_pairs": [], "error": "Pairs must be a non-empty list"}
        
        invalid_pairs = []
        for pair in pairs:
            if not self.validate_pair(pair):
                invalid_pairs.append(pair)
        
        if invalid_pairs:
            return {
                "valid": False,
                "invalid_pairs": invalid_pairs,
                "error": f"Invalid pairs: {', '.join(invalid_pairs)}"
            }
        
        return {"valid": True, "invalid_pairs": []}
