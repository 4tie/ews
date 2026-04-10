import os

from app.utils.json_io import list_json_files, read_json, write_json
from app.utils.paths import resolve_safe, saved_configs_dir, settings_dir

SETTINGS_FILE = "app_settings.json"

_DEFAULT_SETTINGS: dict = {
    "engine": "freqtrade",
    "freqtrade_path": "",
    "user_data_path": "",
    "default_exchange": "binance",
    "default_timeframe": "5m",
    "default_max_open_trades": 3,
    "theme": "dark",
    "results_base_path": "",
    "config_path": "",
}


class ConfigService:
    def _settings_path(self) -> str:
        return os.path.join(settings_dir(), SETTINGS_FILE)

    def get_settings(self) -> dict:
        loaded = read_json(self._settings_path(), fallback=None)
        if isinstance(loaded, dict):
            # Merge defaults with persisted values to keep old settings files working.
            return {**_DEFAULT_SETTINGS, **loaded}
        return dict(_DEFAULT_SETTINGS)

    def save_settings(self, data: dict) -> None:
        write_json(self._settings_path(), data)

    def list_saved_configs(self) -> list[str]:
        return [f[:-5] for f in list_json_files(saved_configs_dir())]

    def load_config(self, name: str) -> dict:
        path = resolve_safe(saved_configs_dir(), f"{name}.json")
        return read_json(path, fallback={})

    def save_config(self, name: str, data: dict) -> None:
        path = resolve_safe(saved_configs_dir(), f"{name}.json")
        write_json(path, data)

    def delete_config(self, name: str) -> None:
        path = resolve_safe(saved_configs_dir(), f"{name}.json")
        if os.path.isfile(path):
            os.remove(path)
