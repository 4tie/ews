from pathlib import Path


ROOT = Path(__file__).resolve().parent
SHARED_DRAWER = ROOT / "web" / "static" / "js" / "components" / "ai-chat-panel.js"
LEGACY_PANEL = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "ai-chat-panel.js"
STATE = ROOT / "web" / "static" / "js" / "core" / "state.js"
PROPOSAL_WORKFLOW = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "proposal-workflow.js"
COMPARE_PANEL = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "compare" / "compare-panel.js"
CANDIDATE_SELECTION_STATE = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "compare" / "candidate-selection-state.js"
DECISION_RENDERER = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "compare" / "decision-ready-renderer.js"


def test_shared_drawer_normalizes_candidate_overlays_with_canonical_precedence():
    source = SHARED_DRAWER.read_text(encoding="utf-8")
    assert "function normalizeCandidateOverlay(entry)" in source
    assert 'assign("candidate_version_id", raw.candidate_version_id || raw.version_id);' in source
    assert 'assign("message", raw.message || raw.note);' in source
    assert '...normalizeCandidateOverlay(message),' in source
    assert '...normalizeCandidateOverlay(overlays?.[message?.id]),' in source
    assert 'candidate_note: candidateMeta.message || "",' in source
    assert 'rememberCandidateOverlay(strategy, messageId, response);' in source


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
        "normalizeCandidateOverlay",
    ):
        assert canonical_token not in source


def test_selected_candidate_state_is_shared_across_backtesting_surfaces():
    state_source = STATE.read_text(encoding="utf-8")
    selection_source = CANDIDATE_SELECTION_STATE.read_text(encoding="utf-8")

    assert "selectedCandidateVersionId" in state_source
    assert 'getState("backtest.selectedCandidateVersionId")' in selection_source
    assert 'setState("backtest.selectedCandidateVersionId", versionId ? String(versionId) : null);' in selection_source
    assert "export function getWorkflowCandidateVersions" in selection_source
    assert "backtest_run:" in selection_source


def test_proposal_workflow_uses_selected_candidate_state_and_decision_ready_compare():
    source = PROPOSAL_WORKFLOW.read_text(encoding="utf-8")

    assert 'data-role="selected-candidate"' in source
    assert "Selected Candidate" in source
    assert "renderDecisionReadyCompare(compareState.data" in source
    assert "setSelectedCandidateVersionId(response.candidate_version_id);" in source
    assert 'onState("backtest.selectedCandidateVersionId", () => {' in source
    assert "ensureSelectedCandidateVersion(versionsState.versions, currentBaselineRunId())" in source
    assert "Candidate Compare" in source


def test_compare_panel_is_workflow_aware_and_preserves_generic_fallback():
    source = COMPARE_PANEL.read_text(encoding="utf-8")

    assert "workflowModeActive" in source
    assert "Baseline" in source
    assert "Selected Candidate" in source
    assert "renderDecisionReadyCompare(lastComparison" in source
    assert "getWorkflowCandidateVersions(versionsState.versions, workflowBaselineRunId())" in source
    assert 'onState("backtest.selectedCandidateVersionId", () => {' in source
    assert "Left run" in source
    assert "Right run" in source
    assert "Decision evidence is grounded in persisted run summaries, request snapshots, and version artifacts only." in source


def test_decision_renderer_exposes_diff_pair_and_diagnosis_sections():
    source = DECISION_RENDERER.read_text(encoding="utf-8")

    assert "Version Diff" in source
    assert "Decision Metrics" in source
    assert "Pair Delta" in source
    assert "Diagnosis Delta" in source
    assert "compare-diff-table" in source
    assert "compare-pairs-table" in source
    assert "compare-diagnosis-grid" in source
    assert "decision-badge--" in source
