from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.models.backtest_models import BacktestRunRequest, ConfigSaveRequest
from app.services.results_service import ResultsService
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.services.config_service import ConfigService

router = APIRouter()
results_svc = ResultsService()
cli_svc = FreqtradeCliService()
config_svc = ConfigService()


@router.get("/options")
async def get_options():
    """Return available strategies, timeframes, and exchanges."""
    return {
        "strategies": cli_svc.list_strategies(),
        "timeframes": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"],
        "exchanges": ["binance", "kucoin", "bybit", "okx", "gate"],
    }


@router.post("/run")
async def run_backtest(payload: BacktestRunRequest):
    """Trigger a freqtrade backtest subprocess."""
    result = cli_svc.run_backtest(payload.model_dump())
    return {"status": "queued", "run_id": "placeholder", "command": result.get("command")}


@router.post("/download-data")
async def download_data(payload: dict):
    """Trigger freqtrade download-data."""
    result = cli_svc.download_data(payload)
    return {"status": "queued", "command": result.get("command")}


@router.get("/summary")
async def get_summary(strategy: str | None = None):
    """Load latest backtest summary for a strategy."""
    if not strategy:
        return {"summary": None}
    summary = results_svc.load_latest_summary(strategy)
    return {"summary": summary}


@router.get("/trades")
async def get_trades(strategy: str | None = None):
    """Load trades from latest backtest summary."""
    if not strategy:
        return {"trades": []}
    trades = results_svc.load_trades(strategy)
    return {"trades": trades}


@router.get("/configs")
async def list_configs():
    return {"configs": config_svc.list_saved_configs()}


@router.post("/configs")
async def save_config(payload: ConfigSaveRequest):
    config_svc.save_config(payload.name, payload.data)
    return {"status": "saved", "name": payload.name}


@router.delete("/configs/{name}")
async def delete_config(name: str):
    config_svc.delete_config(name)
    return {"status": "deleted", "name": name}
