"""Freqtrade-specific backend ownership root."""

from app.freqtrade.cli_service import FreqtradeCLIService, FreqtradeCliService
from app.freqtrade.engine import FreqtradeEngine
from app.freqtrade.result_parser import FreqtradeResultParser

__all__ = [
    "FreqtradeCLIService",
    "FreqtradeCliService",
    "FreqtradeEngine",
    "FreqtradeResultParser",
]
