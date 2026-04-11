import json

import app.freqtrade.cli_service as cli_module
import app.freqtrade.commands as commands
from app.freqtrade.cli_service import FreqtradeCliService


def test_resolve_backtest_raw_result_prefers_meta_with_matching_run_note(tmp_path, monkeypatch):
    service = FreqtradeCliService()
    meta_path = tmp_path / "backtest-result-001.meta.json"
    zip_path = tmp_path / "backtest-result-001.zip"
    meta_path.write_text(json.dumps({"TestStrat": {"notes": "run-123"}}), encoding="utf-8")
    zip_path.write_bytes(b"zip")

    monkeypatch.setattr(service, "_backtest_meta_paths", lambda strategy: [str(meta_path)])

    resolved = service.resolve_backtest_raw_result("TestStrat", "run-123")

    assert resolved == str(zip_path)


def test_resolve_backtest_raw_result_falls_back_to_last_result(tmp_path, monkeypatch):
    service = FreqtradeCliService()
    zip_path = tmp_path / "backtest-result-latest.zip"
    zip_path.write_bytes(b"zip")
    (tmp_path / ".last_result.json").write_text(
        json.dumps({"latest_backtest": zip_path.name}),
        encoding="utf-8",
    )

    monkeypatch.setattr(service, "_backtest_meta_paths", lambda strategy: [])
    monkeypatch.setattr(cli_module, "strategy_results_dir", lambda strategy: str(tmp_path))

    resolved = service.resolve_backtest_raw_result("TestStrat", "run-123")

    assert resolved == str(zip_path)


def test_build_backtest_command_supports_multiple_config_paths(monkeypatch):
    monkeypatch.setattr(commands, "resolve_freqtrade_executable", lambda freqtrade_path: "freqtrade")

    cmd = commands.build_backtest_command(
        freqtrade_path="",
        strategy="TestStrat",
        config_paths=["base.json", "overlay.json"],
        strategy_path="workspace/strategies",
        timeframe="5m",
        timerange="20240101-20240131",
        pairs=["BTC/USDT", "ETH/USDT"],
        dry_run_wallet=1000,
        max_open_trades=3,
        export_mode="trades",
        backtest_directory="results",
        notes="run-123",
        extra_flags=["--cache", "none"],
    )

    assert cmd[:3] == ["freqtrade", "backtesting", "--strategy"]
    assert cmd.count("--config") == 2
    assert "--strategy-path" in cmd
    assert "--backtest-directory" in cmd
    assert "--notes" in cmd
    assert cmd[-2:] == ["--cache", "none"]
