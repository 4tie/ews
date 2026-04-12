from pathlib import Path


ROOT = Path(__file__).resolve().parent
SHARED_DRAWER = ROOT / "web" / "static" / "js" / "components" / "ai-chat-panel.js"
LEGACY_PANEL = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "ai-chat-panel.js"


def test_shared_drawer_prefers_canonical_candidate_fields():
    source = SHARED_DRAWER.read_text(encoding="utf-8")
    assert "candidate_version_id is the canonical field for new workflow code." in source
    assert "Legacy/transitional aliases such as version_id are intentionally not used here." in source
    assert "candidate_version_id" in source


def test_legacy_results_panel_remains_frozen_from_canonical_wiring():
    source = LEGACY_PANEL.read_text(encoding="utf-8")
    assert "Legacy panel: frozen on purpose." in source
    assert "The shared drawer under web/static/js/components/ai-chat-panel.js is the only UI surface" in source
    for canonical_token in (
        "baseline_run_id",
        "baseline_version_id",
        "baseline_run_version_id",
        "baseline_version_source",
        "candidate_ai_mode",
    ):
        assert canonical_token not in source
