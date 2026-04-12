from pathlib import Path


ROOT = Path(__file__).resolve().parent
SHARED_DRAWER = ROOT / "web" / "static" / "js" / "components" / "ai-chat-panel.js"
LEGACY_PANEL = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "ai-chat-panel.js"
API_CLIENT = ROOT / "web" / "static" / "js" / "core" / "api.js"
STATE = ROOT / "web" / "static" / "js" / "core" / "state.js"
BACKTESTING_INDEX = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "index.js"
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


def test_legacy_results_panel_is_removed_from_active_workflow():
    assert not LEGACY_PANEL.exists()

    index_source = BACKTESTING_INDEX.read_text(encoding="utf-8")
    assert "./results/ai-chat-panel.js" not in index_source
    assert "initAiChatPanel" not in index_source


def test_api_client_removed_deprecated_ai_chat_apply_methods():
    source = API_CLIENT.read_text(encoding="utf-8")

    for removed in (
        "applyCode",
        "applyParameters",
        "/api/ai/chat/apply-code",
        "/api/ai/chat/apply-parameters",
    ):
        assert removed not in source

    assert 'createProposalCandidate: (runId, data) => api.post(`/api/backtest/runs/${encodeURIComponent(runId)}/proposal-candidates`, data),' in source
    assert 'compareRuns: (leftRunId, rightRunId) => api.get(`/api/backtest/compare${toQuery({ left_run_id: leftRunId, right_run_id: rightRunId })}`),' in source


def test_shared_drawer_and_workflow_use_canonical_candidate_and_compare_routes():
    drawer_source = SHARED_DRAWER.read_text(encoding="utf-8")
    workflow_source = PROPOSAL_WORKFLOW.read_text(encoding="utf-8")

    assert "api.backtest.createProposalCandidate" in drawer_source
    assert "api.aiChat.apply" not in drawer_source
    assert "/api/ai/chat/apply" not in drawer_source
    assert "api.backtest.createProposalCandidate" in workflow_source
    assert "api.backtest.compareRuns" in workflow_source
    assert "api.aiChat.apply" not in workflow_source
    assert "/api/ai/chat/apply" not in workflow_source


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