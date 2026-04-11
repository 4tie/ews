import json
import os
from typing import Any


def read_json(path: str, fallback: Any = None) -> Any:
    """Safely read a JSON file, returning fallback if missing or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def write_json(path: str, data: Any, indent: int = 2) -> None:
    """Write data to a JSON file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)


def list_json_files(directory: str) -> list[str]:
    """List all .json filenames in a directory."""
    if not os.path.isdir(directory):
        return []
    return [f for f in os.listdir(directory) if f.endswith(".json")]
