"""Freqtrade-specific backend ownership root."""

from importlib import import_module

__all__ = [
    "FreqtradeCLIService",
    "FreqtradeCliService",
    "FreqtradeEngine",
    "FreqtradeResultParser",
]


def __getattr__(name: str):
    if name in {"FreqtradeCLIService", "FreqtradeCliService"}:
        module = import_module("app.freqtrade.cli_service")
        return getattr(module, name)
    if name == "FreqtradeEngine":
        module = import_module("app.freqtrade.engine")
        return getattr(module, name)
    if name == "FreqtradeResultParser":
        module = import_module("app.freqtrade.result_parser")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
