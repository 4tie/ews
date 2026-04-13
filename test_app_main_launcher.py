import app.main as main_module


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
