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


# --- Auto Optimize v1 models ---

class OptimizationRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class OptimizationResultKind(str, Enum):
    FINALISTS_FOUND = "finalists_found"
    NO_PROFITABLE_FINALISTS = "no_profitable_finalists"
    HARD_STOP_TRIGGERED = "hard_stop_triggered"
    FATAL_ERROR = "fatal_error"


class OptimizationCompletionReason(str, Enum):
    FINALISTS_FOUND = "finalists_found"
    NO_PROFITABLE_FINALISTS = "no_profitable_finalists"
    HARD_STOP_TRIGGERED = "hard_stop_triggered"
    FATAL_ERROR = "fatal_error"


class OptimizationThresholds(BaseModel):
    min_profit_total_pct: float = 0.5
    min_total_trades: int = 30
    max_allowed_drawdown_pct: float = 35


class OptimizationHardStops(BaseModel):
    max_total_nodes: Optional[int] = None
    max_failed_runs: Optional[int] = None
    max_consecutive_no_improvement_attempts: int = 3


class OptimizationRunCreateRequest(BaseModel):
    baseline_run_id: str
    attempts: int = Field(default=3, ge=1)
    beam_width: int = Field(default=2, ge=1)
    branch_factor: int = Field(default=3, ge=1)
    include_ai_suggestions: bool = False
    thresholds: OptimizationThresholds = Field(default_factory=OptimizationThresholds)
    hard_stops: OptimizationHardStops = Field(default_factory=OptimizationHardStops)


class OptimizationError(BaseModel):
    error_code: str
    error_stage: str
    message: str
    optimizer_run_id: str
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    suggested_fix: Optional[str] = None


class OptimizationNodeRecord(BaseModel):
    node_id: str
    depth: int = 0
    parent_node_id: Optional[str] = None
    parent_version_id: Optional[str] = None
    parent_run_id: Optional[str] = None

    candidate_descriptor: Optional[str] = None
    candidate_version_id: Optional[str] = None
    run_id: Optional[str] = None
    status: str
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None

    summary_metrics: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None
    constraint_passed: bool = False
    failed_constraints: List[str] = Field(default_factory=list)

    dedup_signature: Optional[str] = None
    dedup_reason: Optional[str] = None

    error: Optional[OptimizationError] = None


class OptimizationFinalist(BaseModel):
    version_id: str
    run_id: str
    summary_metrics: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None


class OptimizationNearMiss(BaseModel):
    node_id: str
    version_id: Optional[str] = None
    run_id: Optional[str] = None
    summary_metrics: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None
    failed_constraints: List[str] = Field(default_factory=list)
    candidate_descriptor: Optional[str] = None


class OptimizationRunRecord(BaseModel):
    schema_version: int = 1
    optimizer_run_id: str
    status: OptimizationRunStatus
    result_kind: Optional[OptimizationResultKind] = None
    completion_reason: Optional[OptimizationCompletionReason] = None

    baseline_run_id: str
    baseline_version_id: Optional[str] = None
    request_snapshot: Dict[str, Any] = Field(default_factory=dict)

    attempts: int
    beam_width: int
    branch_factor: int
    include_ai_suggestions: bool = False
    thresholds: OptimizationThresholds = Field(default_factory=OptimizationThresholds)
    hard_stops: OptimizationHardStops = Field(default_factory=OptimizationHardStops)

    created_at: str
    updated_at: str
    completed_at: Optional[str] = None

    finalists: List[OptimizationFinalist] = Field(default_factory=list)
    near_misses: List[OptimizationNearMiss] = Field(default_factory=list)
    nodes: List[OptimizationNodeRecord] = Field(default_factory=list)

    error: Optional[OptimizationError] = None
