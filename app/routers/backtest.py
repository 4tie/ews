from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from models.backtest_models import BacktestRunRequest, ConfigSaveRequest
from services.results_service import ResultsService
from services.freqtrade_cli_service import FreqtradeCliService
from services.config_service import ConfigService

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
    # TODO: wire to FreqtradeCliService.run_backtest(payload)
    return {"status": "queued", "run_id": "placeholder", "message": "Backtest queued — wiring pending"}


@router.post("/download-data")
async def download_data(payload: dict):
    """Trigger freqtrade download-data."""
    # TODO: wire to FreqtradeCliService.download_data(payload)
    return {"status": "queued", "message": "Data download queued — wiring pending"}


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
