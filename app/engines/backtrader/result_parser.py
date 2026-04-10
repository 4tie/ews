from __future__ import annotations

from app.engines.base import EngineFeatureNotSupported, ParsedBacktestResult, ResultParser
from app.models.backtest_models import BacktestRunRecord


class BacktraderResultParser(ResultParser):
    def parse_backtest_run(self, run_record: BacktestRunRecord) -> ParsedBacktestResult:
        raise EngineFeatureNotSupported(
            "backtrader",
            "result-parsing",
            "Backtrader result parsing is not implemented yet.",
        )
