"""
json_io.py — JSON I/O utilities for reading and writing JSON files with fallbacks.
"""

import json
import os
from typing import Any


def read_json(path: str, fallback: Any = None) -> Any:
    """
    Read JSON file with fallback value on error.
    
    Args:
        path: Path to JSON file
        fallback: Value to return if file doesn't exist or is invalid
    
    Returns:
        Parsed JSON content or fallback value
    """
    if not os.path.isfile(path):
        return fallback
    
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return fallback


def write_json(path: str, data: Any, indent: int = 2) -> None:
    """
    Write data to JSON file, creating parent directories if needed.
    
    Args:
        path: Path to JSON file
        data: Data to serialize
        indent: JSON indentation level
    
    Raises:
        OSError: If file cannot be written
        TypeError: If data is not JSON serializable
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=indent, ensure_ascii=False)


def list_json_files(directory: str) -> list[str]:
    """
    List all JSON files in a directory.
    
    Args:
        directory: Path to directory
    
    Returns:
        List of JSON filenames (not full paths)
    """
    if not os.path.isdir(directory):
        return []
    
    return [f for f in os.listdir(directory) if f.endswith(".json")]
