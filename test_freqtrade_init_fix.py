import os
import subprocess
import sys
from pathlib import Path

from app.freqtrade.cli_service import FreqtradeCliService
from app.freqtrade.executable import resolve_freqtrade_executable


def test_resolve_freqtrade_executable_accepts_explicit_file(tmp_path):
    exe_name = "freqtrade.exe" if sys.platform == "win32" else "freqtrade"
    exe_path = tmp_path / exe_name
    exe_path.write_text("", encoding="utf-8")
    if sys.platform != "win32":
        exe_path.chmod(0o755)

    assert resolve_freqtrade_executable(str(exe_path)) == str(exe_path)


def test_subprocess_env_no_force_threaded(monkeypatch):
    monkeypatch.setenv("FT_FORCE_THREADED_RESOLVER", "1")

    env = FreqtradeCliService()._freqtrade_subprocess_env()

    assert "FT_FORCE_THREADED_RESOLVER" not in env


def test_sitecustomize_safe():
    repo_root = Path(__file__).resolve().parent
    command = [
        sys.executable,
        "-c",
        "import os; os.environ['FT_FORCE_THREADED_RESOLVER']='1'; import sitecustomize; print('ok')",
    ]

    result = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
