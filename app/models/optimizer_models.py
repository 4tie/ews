from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


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
