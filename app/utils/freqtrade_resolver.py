"""Freqtrade executable resolution with validation and PATH auto-detection."""

import os
import shutil
import sys


def resolve_freqtrade_executable(freqtrade_path: str) -> str:
    """
    Resolve the freqtrade executable path with validation and auto-detection.

    Args:
        freqtrade_path: Directory containing freqtrade executable (or project root / venv root),
            an explicit executable path, or empty for PATH auto-detect.

    Returns:
        Full path to freqtrade executable, or "freqtrade" for PATH lookup.

    Raises:
        ValueError: If configured path is invalid or executable not found.
    """
    is_windows = sys.platform == "win32"
    exe_name = "freqtrade.exe" if is_windows else "freqtrade"

    if freqtrade_path:
        path = os.path.abspath(os.path.expanduser(freqtrade_path))

        # Accept an explicit executable file path.
        if os.path.isfile(path):
            base = os.path.basename(path).lower()
            if base not in ("freqtrade", "freqtrade.exe"):
                raise ValueError(f"Freqtrade path is a file, expected {exe_name}: {path}")
            if not is_windows and not os.access(path, os.X_OK):
                raise ValueError(f"Freqtrade not executable: {path}")
            return path

        if not os.path.isdir(path):
            raise ValueError(f"Freqtrade directory not found: {path}")

        candidates = [
            os.path.join(path, exe_name),
            os.path.join(path, "freqtrade"),
        ]

        # Common virtualenv layouts (project root, or venv root).
        if is_windows:
            candidates += [
                os.path.join(path, "Scripts", "freqtrade.exe"),
                os.path.join(path, ".venv", "Scripts", "freqtrade.exe"),
                os.path.join(path, "venv", "Scripts", "freqtrade.exe"),
            ]
        else:
            candidates += [
                os.path.join(path, "bin", "freqtrade"),
                os.path.join(path, ".venv", "bin", "freqtrade"),
                os.path.join(path, "venv", "bin", "freqtrade"),
            ]

        for exe_path in candidates:
            if os.path.isfile(exe_path):
                if not is_windows and not os.access(exe_path, os.X_OK):
                    raise ValueError(f"Freqtrade not executable: {exe_path}")
                return exe_path

        checked = ", ".join(candidates)
        raise ValueError(f"Freqtrade executable not found. Checked: {checked}")

    found = shutil.which("freqtrade")
    if found:
        return found

    return "freqtrade"
