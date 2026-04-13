from pathlib import Path

import app.main as main_module


ROOT = Path(__file__).resolve().parent


def test_app_main_launcher_uses_repo_scoped_reload(monkeypatch):
    captured = {}

    def _chdir(path):
        captured["cwd"] = path

    def _run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(main_module.os, "chdir", _chdir)
    monkeypatch.setattr(main_module.uvicorn, "run", _run)

    main_module.main()

    assert captured["cwd"] == main_module.BASE_DIR
    assert captured["app"] == "app.main:app"
    assert captured["reload"] is True
    assert captured["reload_dirs"] == ["app", "web"]
    assert captured["reload_excludes"] == [
        main_module.os.path.join("data", "backtest_runs", "*", "workspace"),
        main_module.os.path.join("data", "backtest_runs", "*", "workspace", "*"),
        main_module.os.path.join("user_data", "backtest_results", "*"),
        main_module.os.path.join("data", "versions", "*", "*.json"),
    ]


def test_app_main_reload_excludes_cover_workflow_write_paths():
    excludes = main_module._dev_reload_excludes()

    assert main_module.os.path.join("data", "backtest_runs", "*", "workspace") in excludes
    assert main_module.os.path.join("data", "backtest_runs", "*", "workspace", "*") in excludes
    assert main_module.os.path.join("user_data", "backtest_results", "*") in excludes
    assert main_module.os.path.join("data", "versions", "*", "*.json") in excludes


def test_project_docs_point_to_python_app_main_entrypoint():
    for relative_path in ("AGENTS.md", "STATUS.md"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "python app\\main.py" in source
        assert "Do not use raw `uvicorn --reload`" in source
