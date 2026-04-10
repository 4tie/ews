from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BacktestTriggerSource(str, Enum):
    MANUAL = "manual"
    AI_APPLY = "ai_apply"
    EVOLUTION = "evolution"
    OPTIMIZER = "optimizer"


class BacktestRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class BacktestRunRequest(BaseModel):
    strategy: str
    timeframe: str
    timerange: Optional[str] = None
    pairs: List[str] = Field(default_factory=list)
    exchange: str = "binance"
    stake_amount: Optional[float] = None
    max_open_trades: Optional[int] = None
    config_path: Optional[str] = None
    extra_flags: List[str] = Field(default_factory=list)
    version_id: Optional[str] = None
    trigger_source: BacktestTriggerSource = BacktestTriggerSource.MANUAL


class BacktestRunRecord(BaseModel):
    run_id: str
    strategy: str
    version_id: Optional[str] = None
    trigger_source: BacktestTriggerSource
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    status: BacktestRunStatus
    command: str
    artifact_path: Optional[str] = None
    raw_result_path: Optional[str] = None
    result_path: Optional[str] = None
    summary_path: Optional[str] = None
    exit_code: Optional[int] = None
    pid: Optional[int] = None
    error: Optional[str] = None


class ConfigSaveRequest(BaseModel):
    name: str
    data: Dict[str, Any]


class BacktestSummary(BaseModel):
    strategy: str
    timeframe: str
    timerange: Optional[str]
    profit_total_pct: Optional[float]
    win_rate: Optional[float]
    total_trades: Optional[int]
    drawdown_pct: Optional[float]
    sharpe: Optional[float]
    sortino: Optional[float]
    version_id: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class Trade(BaseModel):
    pair: str
    profit_pct: float
    profit_abs: float
    open_date: str
    close_date: str
    duration: str
    is_open: bool = False
