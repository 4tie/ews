from typing import List, Optional

from app.utils.freqtrade_resolver import resolve_freqtrade_executable


def build_backtest_command(
    freqtrade_path: str,
    strategy: str,
    config_path: str,
    timerange: Optional[str] = None,
    pairs: Optional[List[str]] = None,
    timeframe: Optional[str] = None,
    extra_flags: Optional[List[str]] = None,
) -> List[str]:
    """Build a freqtrade backtesting command as a list of args."""
    exe = resolve_freqtrade_executable(freqtrade_path)
    cmd = [
        exe,
        "backtesting",
        "--strategy", strategy,
        "--config", config_path,
    ]
    if timerange:
        cmd += ["--timerange", timerange]
    if timeframe:
        cmd += ["--timeframe", timeframe]
    if pairs:
        cmd += ["--pairs"] + pairs
    if extra_flags:
        cmd += extra_flags
    return cmd


def build_hyperopt_command(
    freqtrade_path: str,
    strategy: str,
    config_path: str,
    epochs: int = 100,
    spaces: Optional[List[str]] = None,
    hyperopt_loss: str = "SharpeHyperOptLoss",
    timerange: Optional[str] = None,
    extra_flags: Optional[List[str]] = None,
) -> List[str]:
    """Build a freqtrade hyperopt command as a list of args."""
    exe = resolve_freqtrade_executable(freqtrade_path)
    cmd = [
        exe,
        "hyperopt",
        "--strategy", strategy,
        "--config", config_path,
        "--epochs", str(epochs),
        "--hyperopt-loss", hyperopt_loss,
    ]
    if spaces:
        cmd += ["--spaces"] + spaces
    if timerange:
        cmd += ["--timerange", timerange]
    if extra_flags:
        cmd += extra_flags
    return cmd


def build_download_command(
    freqtrade_path: str,
    config_path: str,
    pairs: List[str],
    timeframes: List[str],
    timerange: Optional[str] = None,
    prepend: bool = False,
) -> List[str]:
    exe = resolve_freqtrade_executable(freqtrade_path)
    cmd = [
        exe,
        "download-data",
        "--config", config_path,
        "--pairs",
    ] + pairs + ["--timeframes"] + timeframes
    if timerange:
        cmd += ["--timerange", timerange]
    if prepend:
        cmd += ["--prepend"]
    return cmd


def command_to_string(cmd: List[str]) -> str:
    return " ".join(cmd)
