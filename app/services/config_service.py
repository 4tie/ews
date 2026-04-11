import os

from app.freqtrade.settings import get_freqtrade_runtime_settings
from app.utils.json_io import list_json_files, read_json, write_json
from app.utils.paths import (
    legacy_storage_dirs,
    resolve_safe,
    saved_configs_dir,
    settings_dir,
)

SETTINGS_FILE = "app_settings.json"


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

        if not isinstance(loaded, dict):
            candidates = [p for p in self._legacy_settings_candidates() if os.path.isfile(p)]
            if candidates:
                newest = max(candidates, key=os.path.getmtime)
                legacy = read_json(newest, fallback=None)
                if isinstance(legacy, dict):
                    loaded = legacy
                    write_json(self._settings_path(), legacy)

        if isinstance(loaded, dict):
            return get_freqtrade_runtime_settings(loaded)
        return get_freqtrade_runtime_settings()

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
