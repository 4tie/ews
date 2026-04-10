from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timezone
from typing import Any

from app.engines.base import BacktestEngine
from app.models.backtest_models import BacktestRunRecord
from app.services.config_service import ConfigService
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.services.validation_service import ValidationService
from app.utils.datetime_utils import parse_timerange

config_svc = ConfigService()
validation_svc = ValidationService()


class FreqtradeEngine(BacktestEngine):
    engine_id = "freqtrade"
    _SUPPORTED_COVERAGE_EXTENSIONS = (".json", ".json.gz", ".jsongz")
    _KNOWN_DATA_EXTENSIONS = (".json", ".json.gz", ".jsongz", ".feather", ".parquet")

    def __init__(self, cli_service: FreqtradeCliService | None = None):
        self._cli = cli_service or FreqtradeCliService()

    def list_strategies(self) -> list[str]:
        return self._cli.list_strategies()

    def prepare_backtest_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._cli.prepare_backtest_run(payload)

    def run_backtest(self, payload: dict[str, Any], prepared: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._cli.run_backtest(payload, prepared=prepared)

    def resolve_backtest_raw_result_path(self, run_record: BacktestRunRecord) -> str | None:
        return self._cli.resolve_backtest_raw_result(
            run_record.strategy,
            run_record.run_id,
            run_record.created_at,
        )

    def prepare_download_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._cli.prepare_download_data(payload)

    def run_download_data(self, prepared: dict, log_path: str | None = None) -> dict:
        return self._cli.run_download_data(prepared, log_path=log_path)

    def validate_data(
        self,
        pairs: list[str],
        timeframe: str,
        exchange: str | None = None,
        timerange: str | None = None,
    ) -> list[dict[str, Any]]:
        exchange_name, exchange_dir = self._resolve_exchange_dir(exchange)
        requested_start, requested_end = self._requested_timerange_bounds(timerange)
        results: list[dict[str, Any]] = []

        for pair in pairs:
            result = {
                "pair": pair,
                "exchange": exchange_name,
                "timeframe": timeframe,
                "requested_start": self._format_dt(requested_start),
                "requested_end": self._format_dt(requested_end),
            }

            if not validation_svc.validate_pair(pair):
                results.append(
                    {
                        **result,
                        "status": "invalid",
                        "message": "Invalid pair format. Expected BASE/QUOTE.",
                    }
                )
                continue

            pair_file = self._find_pair_file(exchange_dir, pair, timeframe)
            if not pair_file:
                results.append(
                    {
                        **result,
                        "status": "missing",
                        "message": f"No {timeframe} candle file found for {pair} in {exchange_name}.",
                        "file_path": self._default_pair_path(exchange_dir, pair, timeframe),
                    }
                )
                continue

            result["file_path"] = pair_file
            result["file_name"] = os.path.basename(pair_file)

            ext = self._normalized_extension(pair_file)
            if ext not in self._SUPPORTED_COVERAGE_EXTENSIONS:
                results.append(
                    {
                        **result,
                        "status": "unknown",
                        "message": f"Data file exists, but coverage inspection is not supported for {ext or 'this format'}.",
                    }
                )
                continue

            try:
                coverage = self._read_json_ohlcv_coverage(pair_file)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                results.append(
                    {
                        **result,
                        "status": "invalid",
                        "message": f"Data file could not be read: {exc}",
                    }
                )
                continue

            result["candle_count"] = coverage["candle_count"]
            result["coverage_start"] = self._format_dt(coverage["coverage_start"])
            result["coverage_end"] = self._format_dt(coverage["coverage_end"])

            if coverage["candle_count"] == 0:
                results.append(
                    {
                        **result,
                        "status": "empty",
                        "message": "Data file exists but contains no candles.",
                    }
                )
                continue

            missing_segments = self._coverage_gaps(
                coverage_start=coverage["coverage_start"],
                coverage_end=coverage["coverage_end"],
                requested_start=requested_start,
                requested_end=requested_end,
            )
            if missing_segments:
                results.append(
                    {
                        **result,
                        "status": "partial",
                        "message": self._partial_coverage_message(missing_segments, coverage, requested_start, requested_end),
                    }
                )
                continue

            message = "Data file found."
            if requested_start or requested_end:
                message = "Covers the requested timerange."
            results.append(
                {
                    **result,
                    "status": "valid",
                    "message": message,
                }
            )

        return results

    def _resolve_exchange_dir(self, exchange: str | None) -> tuple[str, str]:
        settings = config_svc.get_settings()
        exchange_name = str(exchange or settings.get("default_exchange") or "binance").strip() or "binance"
        user_data_path = settings.get("user_data_path") or self._cli._user_data_path()  # noqa: SLF001
        exchange_dir = os.path.join(user_data_path, "data", exchange_name)
        return exchange_name, exchange_dir

    def _requested_timerange_bounds(self, timerange: str | None) -> tuple[datetime | None, datetime | None]:
        if not timerange:
            return None, None
        start_token, end_token = parse_timerange(timerange)
        return self._parse_date_token(start_token), self._parse_date_token(end_token)

    def _parse_date_token(self, token: str | None) -> datetime | None:
        if not token:
            return None
        parsed = datetime.strptime(token, "%Y%m%d")
        return parsed.replace(tzinfo=timezone.utc)

    def _default_pair_path(self, exchange_dir: str, pair: str, timeframe: str) -> str:
        return os.path.join(exchange_dir, f"{pair.replace('/', '_')}-{timeframe}.json")

    def _pair_file_candidates(self, exchange_dir: str, pair: str, timeframe: str) -> list[str]:
        stem = os.path.join(exchange_dir, f"{pair.replace('/', '_')}-{timeframe}")
        return [f"{stem}{ext}" for ext in self._KNOWN_DATA_EXTENSIONS]

    def _find_pair_file(self, exchange_dir: str, pair: str, timeframe: str) -> str | None:
        for candidate in self._pair_file_candidates(exchange_dir, pair, timeframe):
            if os.path.isfile(candidate):
                return candidate
        return None

    def _normalized_extension(self, path: str) -> str:
        lower = path.lower()
        if lower.endswith(".json.gz"):
            return ".json.gz"
        if lower.endswith(".jsongz"):
            return ".jsongz"
        _, ext = os.path.splitext(lower)
        return ext

    def _read_json_ohlcv_coverage(self, path: str) -> dict[str, Any]:
        open_fn = gzip.open if path.lower().endswith((".json.gz", ".jsongz")) else open
        with open_fn(path, "rt", encoding="utf-8") as handle:
            candles = json.load(handle)

        if not isinstance(candles, list):
            raise ValueError("Expected OHLCV data to be a JSON array")
        if not candles:
            return {
                "candle_count": 0,
                "coverage_start": None,
                "coverage_end": None,
            }

        first_ts = self._extract_candle_timestamp(candles[0])
        last_ts = self._extract_candle_timestamp(candles[-1])
        if first_ts is None or last_ts is None:
            raise ValueError("OHLCV candles are missing a readable timestamp")

        return {
            "candle_count": len(candles),
            "coverage_start": datetime.fromtimestamp(first_ts / 1000, tz=timezone.utc),
            "coverage_end": datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc),
        }

    def _extract_candle_timestamp(self, candle: Any) -> int | None:
        if isinstance(candle, list) and candle:
            return self._coerce_timestamp_ms(candle[0])
        if isinstance(candle, dict):
            for key in ("timestamp", "date_ts", "date", "open_time", "ts"):
                if key in candle:
                    return self._coerce_timestamp_ms(candle[key])
        return None

    def _coerce_timestamp_ms(self, value: Any) -> int | None:
        if isinstance(value, (int, float)):
            if value > 10_000_000_000:
                return int(value)
            return int(value * 1000)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                return self._coerce_timestamp_ms(int(stripped))
            try:
                parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
        return None

    def _coverage_gaps(
        self,
        coverage_start: datetime | None,
        coverage_end: datetime | None,
        requested_start: datetime | None,
        requested_end: datetime | None,
    ) -> list[str]:
        gaps: list[str] = []
        if requested_start and coverage_start and coverage_start > requested_start:
            gaps.append("start")
        if requested_end and coverage_end and coverage_end < requested_end:
            gaps.append("end")
        return gaps

    def _partial_coverage_message(
        self,
        missing_segments: list[str],
        coverage: dict[str, Any],
        requested_start: datetime | None,
        requested_end: datetime | None,
    ) -> str:
        coverage_label = self._range_label(coverage.get("coverage_start"), coverage.get("coverage_end"))
        requested_label = self._range_label(requested_start, requested_end)
        if missing_segments == ["start"]:
            return f"Data starts too late for the requested timerange. Coverage {coverage_label}; requested {requested_label}."
        if missing_segments == ["end"]:
            return f"Data ends too early for the requested timerange. Coverage {coverage_label}; requested {requested_label}."
        return f"Data does not fully cover the requested timerange. Coverage {coverage_label}; requested {requested_label}."

    def _range_label(self, start: datetime | None, end: datetime | None) -> str:
        start_text = self._format_dt(start)
        end_text = self._format_dt(end)
        if start_text and end_text:
            return f"{start_text} to {end_text}"
        if start_text:
            return start_text
        if end_text:
            return end_text
        return "unknown"

    def _format_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
