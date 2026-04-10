"""Filesystem path helpers for the Optimizer app.

Paths here should be explicit, deterministic, and safe to join with untrusted
input via `resolve_safe`.

`STORAGE_DIR` is the canonical app storage root. `LEGACY_STORAGE_DIR` is kept
for backward compatibility and migrations.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = os.path.join(BASE_DIR, "app")

STORAGE_DIR = os.path.join(APP_DIR, "storage")
LEGACY_STORAGE_DIR = os.path.join(APP_DIR, "app", "storage")

USER_DATA_RESULTS_DIR = os.path.join(BASE_DIR, "user_data", "backtest_results")

SAVED_CONFIGS_DIR = os.path.join(STORAGE_DIR, "saved_configs")
SETTINGS_DIR = os.path.join(STORAGE_DIR, "settings")
OPTIMIZER_RUNS_DIR = os.path.join(STORAGE_DIR, "optimizer_runs")
BACKTEST_RUNS_DIR = os.path.join(STORAGE_DIR, "backtest_runs")
DOWNLOAD_RUNS_DIR = os.path.join(STORAGE_DIR, "download_runs")
STRATEGY_VERSIONS_ROOT_DIR = os.path.join(STORAGE_DIR, "versions")
CACHE_DIR = os.path.join(STORAGE_DIR, "cache")


def resolve_safe(base: str, *parts: str) -> str:
    """Join paths and ensure the result stays within the base directory.

    Uses `os.path.commonpath` instead of naive prefix matching.
    """
    if not base:
        raise ValueError("Base path must be a non-empty string")

    base_real = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base_real, *parts))

    base_check = os.path.normcase(base_real)
    target_check = os.path.normcase(target)
    try:
        common = os.path.commonpath([base_check, target_check])
    except ValueError as exc:
        raise ValueError(f"Path traversal detected: {target}") from exc

    if common != base_check:
        raise ValueError(f"Path traversal detected: {target}")

    return target


def app_dir() -> str:
    """Returns the path to the app directory (BASE_DIR/app)."""
    return APP_DIR


def storage_dir() -> str:
    """Returns the path to the app storage directory (BASE_DIR/app/storage)."""
    return STORAGE_DIR


def saved_configs_dir() -> str:
    return SAVED_CONFIGS_DIR


def settings_dir() -> str:
    return SETTINGS_DIR


def optimizer_runs_dir() -> str:
    return OPTIMIZER_RUNS_DIR


def backtest_runs_dir() -> str:
    return BACKTEST_RUNS_DIR


def download_runs_dir() -> str:
    return DOWNLOAD_RUNS_DIR


def strategy_versions_dir(strategy_name: str) -> str:
    return resolve_safe(STRATEGY_VERSIONS_ROOT_DIR, strategy_name)


def strategy_version_file(strategy_name: str, version_id: str) -> str:
    return os.path.join(strategy_versions_dir(strategy_name), f"{version_id}.json")


def strategy_active_version_file(strategy_name: str) -> str:
    return os.path.join(strategy_versions_dir(strategy_name), "active_version.json")


def cache_dir() -> str:
    return CACHE_DIR


def user_data_results_dir() -> str:
    return USER_DATA_RESULTS_DIR


def strategy_results_dir(strategy: str) -> str:
    return resolve_safe(USER_DATA_RESULTS_DIR, strategy)