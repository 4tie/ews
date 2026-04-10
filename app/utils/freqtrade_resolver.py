"""Freqtrade executable resolution with validation and PATH auto-detection."""

import os
import shutil
import sys


def resolve_freqtrade_executable(freqtrade_path: str) -> str:
    """
    Resolve the freqtrade executable path with validation and auto-detection.

    Args:
        freqtrade_path: Directory containing freqtrade executable, or empty for auto-detect

    Returns:
        Full path to freqtrade executable, or "freqtrade" for PATH lookup

    Raises:
        ValueError: If configured path is invalid or executable not found
    """
    # Windows executable extension
    is_windows = sys.platform == "win32"
    exe_name = "freqtrade.exe" if is_windows else "freqtrade"

    # If path provided, validate it
    if freqtrade_path:
        path = os.path.expanduser(freqtrade_path)

        # Check directory exists
        if not os.path.isdir(path):
            raise ValueError(f"Freqtrade directory not found: {path}")

        # Check executable exists
        exe_path = os.path.join(path, exe_name)
        if not os.path.isfile(exe_path):
            # Also check without .exe extension on Windows
            alt_path = os.path.join(path, "freqtrade")
            if not os.path.isfile(alt_path):
                raise ValueError(f"Freqtrade executable not found in: {path}")
            exe_path = alt_path

        # Check executable permissions (Unix only)
        if not is_windows and not os.access(exe_path, os.X_OK):
            raise ValueError(f"Freqtrade not executable: {exe_path}")

        return exe_path

    # No path configured - try to find in PATH
    found = shutil.which("freqtrade")
    if found:
        return found

    # Fallback to just the command name (will fail at runtime if not in PATH)
    return "freqtrade"
