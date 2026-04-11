from fastapi.testclient import TestClient

from app.main import app
from app.routers import backtest as backtest_router


client = TestClient(app)


async def _fake_get_options():
    return {
        "strategies": ["TestStrat"],
        "timeframes": ["5m"],
        "exchanges": ["binance"],
    }


async def _fake_run_backtest(payload):
    return {
        "status": "running",
        "run_id": "bt-123",
        "command": "freqtrade backtesting",
        "version_id": payload.version_id,
        "trigger_source": payload.trigger_source.value,
    }


async def _fake_download_data(payload):
    return {
        "status": "running",
        "download_id": "dl-123",
        "command": "freqtrade download-data",
        "artifact_path": "download.log",
    }


async def _fake_list_backtest_runs(strategy=None):
    return {"runs": [{"run_id": "bt-123", "strategy": strategy or "TestStrat"}]}


async def _fake_get_backtest_run(run_id):
    return {"run": {"run_id": run_id, "strategy": "TestStrat"}}


async def _fake_compare_backtest_runs(left_run_id, right_run_id):
    return {
        "left_run_id": left_run_id,
        "right_run_id": right_run_id,
        "delta": {"profit_total_pct": 1.25},
    }


async def _fake_validate_data(payload):
    return {
        "valid": True,
        "message": "All pairs cover the requested data range.",
        "summary": {"pair_count": len(payload.get("pairs", []))},
        "results": [],
    }


def test_backtest_route_contract_smoke(monkeypatch):
    monkeypatch.setattr(backtest_router.runtime, "get_options", _fake_get_options)
    monkeypatch.setattr(backtest_router.runtime, "run_backtest", _fake_run_backtest)
    monkeypatch.setattr(backtest_router.runtime, "download_data", _fake_download_data)
    monkeypatch.setattr(backtest_router.runtime, "list_backtest_runs", _fake_list_backtest_runs)
    monkeypatch.setattr(backtest_router.runtime, "get_backtest_run", _fake_get_backtest_run)
    monkeypatch.setattr(backtest_router.runtime, "compare_backtest_runs", _fake_compare_backtest_runs)
    monkeypatch.setattr(backtest_router.runtime, "validate_data", _fake_validate_data)

    options_response = client.get("/api/backtest/options")
    assert options_response.status_code == 200
    assert options_response.json()["strategies"] == ["TestStrat"]

    run_response = client.post(
        "/api/backtest/run",
        json={
            "strategy": "TestStrat",
            "timeframe": "5m",
            "pairs": ["BTC/USDT"],
            "exchange": "binance",
        },
    )
    assert run_response.status_code == 200
    assert run_response.json()["run_id"] == "bt-123"

    download_response = client.post(
        "/api/backtest/download-data",
        json={
            "pairs": ["BTC/USDT"],
            "timeframe": "5m",
        },
    )
    assert download_response.status_code == 200
    assert download_response.json()["download_id"] == "dl-123"

    runs_response = client.get("/api/backtest/runs", params={"strategy": "TestStrat"})
    assert runs_response.status_code == 200
    assert runs_response.json()["runs"][0]["strategy"] == "TestStrat"

    run_detail_response = client.get("/api/backtest/runs/bt-123")
    assert run_detail_response.status_code == 200
    assert run_detail_response.json()["run"]["run_id"] == "bt-123"

    compare_response = client.get(
        "/api/backtest/compare",
        params={"left_run_id": "bt-1", "right_run_id": "bt-2"},
    )
    assert compare_response.status_code == 200
    assert compare_response.json()["delta"]["profit_total_pct"] == 1.25

    validate_response = client.post(
        "/api/backtest/validate-data",
        json={
            "pairs": ["BTC/USDT", "ETH/USDT"],
            "timeframe": "5m",
            "exchange": "binance",
        },
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["valid"] is True
    assert validate_response.json()["summary"]["pair_count"] == 2
