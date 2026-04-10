import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = os.path.join(BASE_DIR, "app")
LEGACY_STORAGE_DIR = os.path.join(APP_DIR, "app", "storage")


def app_dir() -> str:
    """Returns the path to the app directory (BASE_DIR/app)."""
    return APP_DIR


def _migrate_legacy_storage(target_dir: str) -> None:
    """Copy legacy app/app/storage contents into app/storage without overwriting newer files."""
    if not os.path.isdir(LEGACY_STORAGE_DIR):
        return

    os.makedirs(target_dir, exist_ok=True)

    for root_dir, _, files in os.walk(LEGACY_STORAGE_DIR):
        relative_dir = os.path.relpath(root_dir, LEGACY_STORAGE_DIR)
        target_root = target_dir if relative_dir == "." else os.path.join(target_dir, relative_dir)
        os.makedirs(target_root, exist_ok=True)

        for file_name in files:
            source_file = os.path.join(root_dir, file_name)
            target_file = os.path.join(target_root, file_name)
            if not os.path.exists(target_file):
                shutil.copy2(source_file, target_file)


def storage_dir() -> str:
    """Returns the path to the app storage directory (BASE_DIR/app/storage)."""
    target_dir = os.path.join(app_dir(), "storage")
    _migrate_legacy_storage(target_dir)
    return target_dir


def saved_configs_dir() -> str:
    return os.path.join(storage_dir(), "saved_configs")


def settings_dir() -> str:
    return os.path.join(storage_dir(), "settings")


def optimizer_runs_dir() -> str:
    return os.path.join(storage_dir(), "optimizer_runs")


def backtest_runs_dir() -> str:
    return os.path.join(storage_dir(), "backtest_runs")

def download_runs_dir() -> str:
    return os.path.join(storage_dir(), "download_runs")


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
