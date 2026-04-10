from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class VersionStatus(str, Enum):
    DRAFT = "draft"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ChangeType(str, Enum):
    INITIAL = "initial"
    CODE_CHANGE = "code_change"
    PARAMETER_CHANGE = "parameter_change"
    EVOLUTION = "evolution"
    MANUAL = "manual"
    ROLLBACK = "rollback"


class StrategyVersion(BaseModel):
    version_id: str
    parent_version_id: Optional[str] = None
    strategy_name: str
    created_at: str
    created_by: str
    change_type: ChangeType
    summary: str
    diff_ref: Optional[str] = None
    source_ref: Optional[str] = None
    status: VersionStatus = VersionStatus.DRAFT
    
    code_snapshot: Optional[str] = None
    parameters_snapshot: Optional[Dict[str, Any]] = None
    
    backtest_run_id: Optional[str] = None
    backtest_profit_pct: Optional[float] = None
    
    promoted_from_version_id: Optional[str] = None
    promoted_at: Optional[str] = None


class MutationRequest(BaseModel):
    strategy_name: str
    change_type: ChangeType
    summary: str
    created_by: str = "system"
    
    code: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    
    parent_version_id: Optional[str] = None
    source_ref: Optional[str] = None
    diff_ref: Optional[str] = None


class MutationResult(BaseModel):
    version_id: str
    status: str
    message: str


class AcceptRequest(BaseModel):
    version_id: str
    notes: Optional[str] = None


class RollbackRequest(BaseModel):
    target_version_id: str
    reason: Optional[str] = None


class RejectRequest(BaseModel):
    version_id: str
    reason: Optional[str] = None


class VersionListResponse(BaseModel):
    strategy_name: str
    versions: List[StrategyVersion]
    active_version_id: Optional[str] = None


class OptimizerRunRequest(BaseModel):
    strategy: str
    timeframe: str
    timerange: Optional[str] = None
    pairs: List[str] = Field(default_factory=list)
    exchange: str = "binance"
    epochs: int = 100
    spaces: List[str] = Field(default_factory=lambda: ["buy", "sell"])
    hyperopt_loss: str = "SharpeHyperOptLoss"
    seed_from_backtest: bool = False
    extra_flags: List[str] = Field(default_factory=list)


class OptimizerCheckpoint(BaseModel):
    checkpoint_id: str
    epoch: int
    profit_pct: Optional[float]
    created_at: str
    params: Dict[str, Any] = Field(default_factory=dict)


class OptimizerResult(BaseModel):
    run_id: str
    status: str
    best_epoch: Optional[int]
    best_profit_pct: Optional[float]
    checkpoints: List[OptimizerCheckpoint] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)
