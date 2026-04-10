import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_dir() -> str:
    """Returns the path to the app directory (BASE_DIR/app)."""
    return os.path.join(BASE_DIR, "app")


def storage_dir() -> str:
    """Returns the path to the app storage directory (BASE_DIR/app/storage)."""
    return os.path.join(BASE_DIR, "app", "storage")


def saved_configs_dir() -> str:
    return os.path.join(storage_dir(), "saved_configs")


def settings_dir() -> str:
    return os.path.join(storage_dir(), "settings")


def optimizer_runs_dir() -> str:
    return os.path.join(storage_dir(), "optimizer_runs")


def strategy_versions_dir(strategy_name: str) -> str:
    return os.path.join(storage_dir(), "versions", strategy_name)


def strategy_version_file(strategy_name: str, version_id: str) -> str:
    return os.path.join(strategy_versions_dir(strategy_name), f"{version_id}.json")


def strategy_active_version_file(strategy_name: str) -> str:
    return os.path.join(strategy_versions_dir(strategy_name), "active_version.json")


def cache_dir() -> str:
    return os.path.join(storage_dir(), "cache")


def user_data_results_dir() -> str:
    return os.path.join(BASE_DIR, "user_data", "backtest_results")


def strategy_results_dir(strategy: str) -> str:
    return os.path.join(user_data_results_dir(), strategy)


def resolve_safe(base: str, *parts: str) -> str:
    """Join paths and ensure the result stays within the base directory."""
    target = os.path.realpath(os.path.join(base, *parts))
    if not target.startswith(os.path.realpath(base)):
        raise ValueError(f"Path traversal detected: {target}")
    return target
