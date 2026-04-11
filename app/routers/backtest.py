from fastapi import APIRouter

from app.freqtrade import runtime as freqtrade_runtime
from app.models.backtest_models import BacktestRunRequest, ConfigSaveRequest, ProposalCandidateRequest

router = APIRouter()
runtime = freqtrade_runtime
config_svc = freqtrade_runtime.config_svc
results_svc = freqtrade_runtime.results_svc
validation_svc = freqtrade_runtime.validation_svc
persistence = freqtrade_runtime.persistence
_resolve_engine = freqtrade_runtime._resolve_engine
_reconcile_stale_backtest_run = freqtrade_runtime._reconcile_stale_backtest_run
_watch_backtest_process = freqtrade_runtime._watch_backtest_process


@router.get("/options")
async def get_options():
    return await runtime.get_options()


@router.post("/run")
async def run_backtest(payload: BacktestRunRequest):
    return await runtime.run_backtest(payload)


@router.post("/download-data")
async def download_data(payload: dict):
    return await runtime.download_data(payload)


@router.get("/runs/{run_id}/logs/stream")
async def stream_backtest_logs(run_id: str):
    return await runtime.stream_backtest_logs(run_id)


@router.get("/download-data/{download_id}/logs/stream")
async def stream_download_logs(download_id: str):
    return await runtime.stream_download_logs(download_id)


@router.get("/runs")
async def list_backtest_runs(strategy: str | None = None):
    return await runtime.list_backtest_runs(strategy)


@router.get("/runs/{run_id}")
async def get_backtest_run(run_id: str):
    return await runtime.get_backtest_run(run_id)


@router.get("/runs/{run_id}/diagnosis")
async def get_backtest_run_diagnosis(run_id: str, include_ai: bool = False):
    return await runtime.get_backtest_run_diagnosis(run_id, include_ai=include_ai)


@router.post("/runs/{run_id}/proposal-candidates")
async def create_backtest_run_proposal_candidate(run_id: str, payload: ProposalCandidateRequest):
    return await runtime.create_backtest_run_proposal_candidate(run_id, payload)


@router.get("/compare")
async def compare_backtest_runs(left_run_id: str, right_run_id: str):
    return await runtime.compare_backtest_runs(left_run_id, right_run_id)


@router.get("/summary")
async def get_summary(strategy: str | None = None):
    return await runtime.get_summary(strategy)


@router.get("/trades")
async def get_trades(strategy: str | None = None):
    return await runtime.get_trades(strategy)


@router.get("/configs")
async def list_configs():
    return await runtime.list_configs()


@router.post("/configs")
async def save_config(payload: ConfigSaveRequest):
    return await runtime.save_config(payload)


@router.get("/configs/{name}")
async def load_config(name: str):
    return await runtime.load_config(name)


@router.delete("/configs/{name}")
async def delete_config(name: str):
    return await runtime.delete_config(name)


@router.post("/validate-data")
async def validate_data(payload: dict):
    return await runtime.validate_data(payload)
