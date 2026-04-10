from typing import List, Optional


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
    cmd = [
        f"{freqtrade_path}/freqtrade" if freqtrade_path else "freqtrade",
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
    cmd = [
        f"{freqtrade_path}/freqtrade" if freqtrade_path else "freqtrade",
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
) -> List[str]:
    cmd = [
        f"{freqtrade_path}/freqtrade" if freqtrade_path else "freqtrade",
        "download-data",
        "--config", config_path,
        "--pairs",
    ] + pairs + ["--timeframes"] + timeframes
    if timerange:
        cmd += ["--timerange", timerange]
    return cmd


def command_to_string(cmd: List[str]) -> str:
    return " ".join(cmd)
