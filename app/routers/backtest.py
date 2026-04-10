import os
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models.backtest_models import (
    BacktestRunRecord,
    BacktestRunRequest,
    BacktestRunStatus,
    ConfigSaveRequest,
)
from app.services.config_service import ConfigService
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.services.mutation_service import mutation_service
from app.services.persistence_service import PersistenceService
from app.services.results_service import ResultsService
from app.utils.datetime_utils import now_iso

router = APIRouter()
results_svc = ResultsService()
cli_svc = FreqtradeCliService()
config_svc = ConfigService()
persistence = PersistenceService()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "data")


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
    version = None
    if payload.version_id:
        version = mutation_service.get_version_by_id(payload.version_id)
        if not version:
            raise HTTPException(status_code=404, detail=f"Version {payload.version_id} not found")
        if version.strategy_name != payload.strategy:
            raise HTTPException(
                status_code=400,
                detail=f"Version {payload.version_id} belongs to {version.strategy_name}, not {payload.strategy}",
            )

    payload_data = payload.model_dump(mode="json")
    command = cli_svc.build_backtest_command_preview(payload_data)
    run_id = f"bt-{uuid.uuid4().hex[:8]}"
    created_at = now_iso()

    run_record = BacktestRunRecord(
        run_id=run_id,
        strategy=payload.strategy,
        version_id=payload.version_id,
        trigger_source=payload.trigger_source,
        created_at=created_at,
        updated_at=created_at,
        status=BacktestRunStatus.QUEUED,
        command=command,
        artifact_path=None,
        pid=None,
        error=None,
    )
    persistence.save_backtest_run(run_id, run_record.model_dump(mode="json"))

    if version is not None:
        mutation_service.link_backtest(version.version_id, run_id, None)

    launch_payload = {**payload_data, "run_id": run_id}

    try:
        result = cli_svc.run_backtest(launch_payload)
    except Exception as exc:
        failed_at = now_iso()
        run_record.status = BacktestRunStatus.FAILED
        run_record.updated_at = failed_at
        run_record.artifact_path = None
        run_record.pid = None
        run_record.error = str(exc)
        persistence.save_backtest_run(run_id, run_record.model_dump(mode="json"))
        return {
            "status": run_record.status.value,
            "run_id": run_id,
            "command": run_record.command,
            "version_id": run_record.version_id,
            "trigger_source": run_record.trigger_source.value,
            "artifact_path": run_record.artifact_path,
            "error": run_record.error,
        }

    run_record.status = BacktestRunStatus.RUNNING
    run_record.updated_at = now_iso()
    run_record.command = result.get("command", run_record.command)
    run_record.artifact_path = result.get("log_file")
    run_record.pid = result.get("pid")
    run_record.error = None
    persistence.save_backtest_run(run_id, run_record.model_dump(mode="json"))

    return {
        "status": run_record.status.value,
        "run_id": run_id,
        "command": run_record.command,
        "version_id": run_record.version_id,
        "trigger_source": run_record.trigger_source.value,
        "artifact_path": run_record.artifact_path,
    }


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


@router.post("/validate-data")
async def validate_data(payload: dict):
    """Validate which pairs have existing candle data files."""
    pairs = payload.get("pairs", [])
    timeframe = payload.get("timeframe", "")

    if not pairs:
        return JSONResponse(
            status_code=400,
            content={"valid": False, "message": "No pairs provided", "results": []}
        )

    results = []

    for pair in pairs:
        pair_file = os.path.join(DATA_DIR, pair.replace("/", "_"), f"{timeframe}.json")
        if os.path.exists(pair_file):
            results.append({"pair": pair, "status": "valid", "message": "Data available"})
        else:
            results.append({"pair": pair, "status": "missing", "message": "No data file found"})

    has_data = any(r["status"] == "valid" for r in results)

    return {
        "valid": has_data,
        "message": f"Found data for {sum(1 for r in results if r['status'] == 'valid')} of {len(pairs)} pairs" if has_data else "No data found for any pairs",
        "results": results
    }
