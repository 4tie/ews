import os

from app.utils.json_io import list_json_files, read_json, write_json
from app.utils.paths import (
    legacy_storage_dirs,
    resolve_safe,
    saved_configs_dir,
    settings_dir,
    user_data_dir,
    user_data_results_dir,
)

SETTINGS_FILE = "app_settings.json"

_DEFAULT_SETTINGS: dict = {
    "engine": "freqtrade",
    "freqtrade_path": "",
    "user_data_path": user_data_dir(),
    "default_exchange": "binance",
    "default_timeframe": "5m",
    "default_max_open_trades": 3,
    "default_timerange": "",
    "default_dry_run_wallet": 1000.0,
    "theme": "dark",
    "results_base_path": user_data_results_dir(),
    "config_path": os.path.join(user_data_dir(), "config.json"),
}


class ConfigService:
    def _settings_path(self) -> str:
        return os.path.join(settings_dir(), SETTINGS_FILE)

    def _legacy_settings_candidates(self) -> list[str]:
        return [
            os.path.join(root, "settings", SETTINGS_FILE)
            for root in legacy_storage_dirs()
        ]

    def get_settings(self) -> dict:
        loaded = read_json(self._settings_path(), fallback=None)

        # Soft migration: if the new path is empty, try legacy locations.
        if not isinstance(loaded, dict):
            candidates = [p for p in self._legacy_settings_candidates() if os.path.isfile(p)]
            if candidates:
                newest = max(candidates, key=os.path.getmtime)
                legacy = read_json(newest, fallback=None)
                if isinstance(legacy, dict):
                    loaded = legacy
                    write_json(self._settings_path(), legacy)

        if isinstance(loaded, dict):
            # Merge defaults with persisted values to keep old settings files working.
            return {**_DEFAULT_SETTINGS, **loaded}
        return dict(_DEFAULT_SETTINGS)

    def save_settings(self, data: dict) -> None:
        write_json(self._settings_path(), data)

    def _legacy_saved_configs_dirs(self) -> list[str]:
        return [os.path.join(root, "saved_configs") for root in legacy_storage_dirs()]

    def list_saved_configs(self) -> list[str]:
        names = {f[:-5] for f in list_json_files(saved_configs_dir())}
        for directory in self._legacy_saved_configs_dirs():
            for filename in list_json_files(directory):
                names.add(filename[:-5])
        return sorted(names)

    def load_config(self, name: str) -> dict:
        path = resolve_safe(saved_configs_dir(), f"{name}.json")
        if not os.path.isfile(path):
            for directory in self._legacy_saved_configs_dirs():
                legacy_path = resolve_safe(directory, f"{name}.json")
                if os.path.isfile(legacy_path):
                    path = legacy_path
                    break
        return read_json(path, fallback={})

    def save_config(self, name: str, data: dict) -> None:
        path = resolve_safe(saved_configs_dir(), f"{name}.json")
        write_json(path, data)

    def delete_config(self, name: str) -> None:
        candidates = [resolve_safe(saved_configs_dir(), f"{name}.json")]
        for directory in self._legacy_saved_configs_dirs():
            candidates.append(resolve_safe(directory, f"{name}.json"))

        for path in candidates:
            if os.path.isfile(path):
                os.remove(path)