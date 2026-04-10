"""\
Engine selection tests.

This repo uses lightweight script-style tests (no pytest dependency).
"""

from __future__ import annotations

import json
import os
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.engines.resolver import resolve_engine, resolve_engine_id
from app.models.settings_models import AppSettings
from app.routers import backtest as backtest_router
from app.services import config_service as config_module
from app.services import freqtrade_cli_service as ft_module
from app.services.config_service import ConfigService


def test_default_engine_is_freqtrade() -> None:
    assert resolve_engine_id({}) == "freqtrade"
    assert AppSettings().engine == "freqtrade"
    engine = resolve_engine({})
    assert engine.engine_id == "freqtrade"
    print("[PASS] Default engine is freqtrade")


def test_invalid_engine_value_fails_validation() -> None:
    try:
        AppSettings(engine="nope")
        raise AssertionError("Expected ValidationError for invalid engine")
    except ValidationError as exc:
        msg = str(exc)
        assert "engine" in msg
        print("[PASS] Invalid engine is rejected by settings schema")


def test_old_settings_file_without_engine_still_works() -> None:
    original_settings_dir = config_module.settings_dir

    with tempfile.TemporaryDirectory() as tmp:
        config_module.settings_dir = lambda: tmp
        try:
            settings_path = os.path.join(tmp, "app_settings.json")
            with open(settings_path, "w", encoding="utf-8") as handle:
                json.dump({"freqtrade_path": "X"}, handle)

            svc = ConfigService()
            settings = svc.get_settings()
            assert settings.get("engine") == "freqtrade"
            assert settings.get("freqtrade_path") == "X"
            print("[PASS] Old settings files without engine get default")
        finally:
            config_module.settings_dir = original_settings_dir


def test_backtest_router_freqtrade_options_still_works() -> None:
    app = FastAPI()
    app.include_router(backtest_router.router, prefix="/api/backtest")
    client = TestClient(app)

    original_router_get_settings = backtest_router.config_svc.get_settings
    original_ft_get_settings = ft_module.config_svc.get_settings

    try:
        backtest_router.config_svc.get_settings = lambda: {"engine": "freqtrade"}
        ft_module.config_svc.get_settings = lambda: {"freqtrade_path": "", "user_data_path": ""}

        resp = client.get("/api/backtest/options")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert "strategies" in payload and isinstance(payload["strategies"], list)
        assert "timeframes" in payload and isinstance(payload["timeframes"], list)
        assert "exchanges" in payload and isinstance(payload["exchanges"], list)
        print("[PASS] Engine=freqtrade still serves /options")
    finally:
        backtest_router.config_svc.get_settings = original_router_get_settings
        ft_module.config_svc.get_settings = original_ft_get_settings


def test_backtest_router_resolves_backtrader_engine() -> None:
    app = FastAPI()
    app.include_router(backtest_router.router, prefix="/api/backtest")
    client = TestClient(app)

    original_get_settings = backtest_router.config_svc.get_settings
    try:
        backtest_router.config_svc.get_settings = lambda: {"engine": "backtrader"}
        resp = client.get("/api/backtest/options")
        assert resp.status_code == 501, resp.text
        assert "backtrader" in resp.text.lower()
        print("[PASS] Engine=backtrader routes through Backtrader engine (501 scaffold)")
    finally:
        backtest_router.config_svc.get_settings = original_get_settings


def test_backtest_router_rejects_unknown_engine() -> None:
    app = FastAPI()
    app.include_router(backtest_router.router, prefix="/api/backtest")
    client = TestClient(app)

    original_get_settings = backtest_router.config_svc.get_settings
    try:
        backtest_router.config_svc.get_settings = lambda: {"engine": "wat"}
        resp = client.get("/api/backtest/options")
        assert resp.status_code == 400, resp.text
        assert "unknown engine" in resp.text.lower()
        print("[PASS] Unknown engine is rejected with HTTP 400")
    finally:
        backtest_router.config_svc.get_settings = original_get_settings


if __name__ == "__main__":
    test_default_engine_is_freqtrade()
    test_invalid_engine_value_fails_validation()
    test_old_settings_file_without_engine_still_works()
    test_backtest_router_freqtrade_options_still_works()
    test_backtest_router_resolves_backtrader_engine()
    test_backtest_router_rejects_unknown_engine()
    print("\n[SUCCESS] Engine selection tests passed!")
