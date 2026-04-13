from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
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


class AcceptPromotionMode(str, Enum):
    ACCEPT_CURRENT = "accept_current"
    PROMOTE_NEW_STRATEGY = "promote_new_strategy"


class VersionAuditEvent(BaseModel):
    event_type: Literal["created", "accepted", "rejected", "rolled_back", "promoted_as_new_strategy"]
    created_at: str
    actor: str
    note: Optional[str] = None
    from_version_id: Optional[str] = None


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
    source_kind: Optional[str] = None
    source_context: Dict[str, Any] = Field(default_factory=dict)
    status: VersionStatus = VersionStatus.DRAFT

    code_snapshot: Optional[str] = None
    parameters_snapshot: Optional[Dict[str, Any]] = None

    backtest_run_id: Optional[str] = None
    backtest_profit_pct: Optional[float] = None

    promoted_from_version_id: Optional[str] = None
    promoted_at: Optional[str] = None
    audit_events: List[VersionAuditEvent] = Field(default_factory=list)


class MutationRequest(BaseModel):
    strategy_name: str
    change_type: ChangeType
    summary: str
    created_by: str = "system"

    code: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

    parent_version_id: Optional[str] = None
    source_ref: Optional[str] = None
    source_kind: Optional[str] = None
    source_context: Dict[str, Any] = Field(default_factory=dict)
    diff_ref: Optional[str] = None


class MutationResult(BaseModel):
    version_id: str
    status: str
    message: str


class AcceptRequest(BaseModel):
    version_id: str
    notes: Optional[str] = None
    promotion_mode: AcceptPromotionMode = AcceptPromotionMode.ACCEPT_CURRENT
    new_strategy_name: Optional[str] = None


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
