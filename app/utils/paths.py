"""Filesystem path helpers for the Optimizer app.

Canonical layout:
- App-owned state (settings, saved configs, run metadata, versions, cache): `./data/`
- Freqtrade state (config, strategies, data, results): `./user_data/`

Use `resolve_safe` for joining untrusted input.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = os.path.join(BASE_DIR, "app")

DATA_DIR = os.path.join(BASE_DIR, "data")
STORAGE_DIR = DATA_DIR

# Pre-data/ storage roots kept for reference and manual migrations.
LEGACY_STORAGE_DIRS = (
    os.path.join(APP_DIR, "storage"),
    os.path.join(APP_DIR, "app", "storage"),
)

USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")
USER_DATA_RESULTS_DIR = os.path.join(USER_DATA_DIR, "backtest_results")

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


def data_dir() -> str:
    """Returns the path to the app data directory (BASE_DIR/data)."""
    return DATA_DIR


def legacy_storage_dirs() -> tuple[str, ...]:
    """Returns legacy (pre-data/) storage roots."""
    return LEGACY_STORAGE_DIRS


def storage_dir() -> str:
    """Returns the path to the app storage directory (BASE_DIR/data)."""
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


def user_data_dir() -> str:
    """Returns the path to the freqtrade user_data directory (BASE_DIR/user_data)."""
    return USER_DATA_DIR


def user_data_results_dir() -> str:
    return USER_DATA_RESULTS_DIR


def strategy_results_dir(strategy: str) -> str:
    return resolve_safe(USER_DATA_RESULTS_DIR, strategy)


def _resolved_user_data_dir(user_data_path: str | None = None) -> str:
    return os.path.realpath(user_data_path or USER_DATA_DIR)


def default_freqtrade_config_path(user_data_path: str | None = None) -> str:
    return os.path.join(_resolved_user_data_dir(user_data_path), "config.json")


def live_strategy_file(strategy_name: str, user_data_path: str | None = None) -> str:
    return resolve_safe(_resolved_user_data_dir(user_data_path), "strategies", f"{strategy_name}.py")


def strategy_config_file(strategy_name: str, user_data_path: str | None = None) -> str:
    return resolve_safe(_resolved_user_data_dir(user_data_path), "config", f"config_{strategy_name}.json")
