import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SHARED_DRAWER = ROOT / "web" / "static" / "js" / "components" / "ai-chat-panel.js"
SHARED_DRAWER_CSS = ROOT / "web" / "static" / "css" / "components" / "ai-chat-panel.css"
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
    assert 'assign("candidate_change_type", raw.candidate_change_type);' in source
    assert 'assign("candidate_status", raw.candidate_status);' in source
    assert 'assign("message", raw.message || raw.note);' in source
    assert '...normalizeCandidateOverlay(message),' in source
    assert '...normalizeCandidateOverlay(overlays?.[message?.id]),' in source
    assert 'candidate_note: candidateMeta.message || "",' in source
    assert 'rememberCandidateOverlay(strategy, messageId, response);' in source


def test_shared_drawer_copy_payload_and_redo_are_data_driven_and_accessible():
    source = SHARED_DRAWER.read_text(encoding="utf-8")

    assert 'import { copyToClipboard } from "../core/utils.js";' in source
    assert "function payloadText(message, payloadKind)" in source
    assert "JSON.stringify(message.parameters, null, 2)" in source
    assert "return message.code.trim();" in source
    assert "function messageContentForCopy(message)" in source
    assert "innerText" not in source

    for token in (
        'action: "copy-payload"',
        'action: "copy-message"',
        'data-action="redo-message"',
        'aria-label="${escapeHtml(label)}"',
        'aria-label="Regenerate response"',
        "source_user_message_id",
        "redo_of_message_id",
        "findSourceUserMessage",
        "api.aiChat.createThreadMessage",
    ):
        assert token in source

    assert "/api/ai/chat/threads" not in source
    assert "api.backtest.createProposalCandidate" in source


def test_shared_drawer_action_policy_and_soft_failure_copy_are_explicit():
    source = SHARED_DRAWER.read_text(encoding="utf-8")

    assert "const canStage = Boolean(currentPayload && currentRunReady() && !state.requestInFlight);" in source
    assert 'state.requestInFlight ? " disabled" : ""' in source
    assert "No run/diagnosis context yet. Load a completed run before staging a candidate." in source
    assert "Candidate staging unavailable for this message until a completed run diagnosis is loaded." in source
    assert "Redo unavailable because no source user prompt was found." in source
    assert "Nothing to copy for this message." in source
    assert "Nothing to copy for this payload." in source


def test_shared_drawer_css_uses_theme_tokens_and_accessible_controls():
    source = SHARED_DRAWER_CSS.read_text(encoding="utf-8")

    forbidden_tokens = (
        "#0b141a",
        "#202c33",
        "#232d36",
        "#2a3a47",
        "#0f1a23",
        "#26a69a",
        "#58a6ff",
        "--color-surface-1",
        "rgba(",
    )
    for token in forbidden_tokens:
        assert token not in source

    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)
    assert "var(--color-bg)" in source
    assert "var(--color-surface)" in source
    assert "var(--color-surface-2)" in source
    assert "var(--color-border)" in source
    assert "color-mix(in srgb" in source
    assert "prefers-reduced-motion: reduce" in source
    assert ":focus-visible" in source
    assert ".ai-chat-message:hover .ai-chat-copy-message-btn" in source
    assert ".ai-chat-message:focus-within .ai-chat-copy-message-btn" in source
    assert ".ai-chat-message__payload-actions" in source
    assert ".ai-chat-redo-row" in source


def test_legacy_results_panel_is_removed_from_active_workflow():
    assert not LEGACY_PANEL.exists()

    index_source = BACKTESTING_INDEX.read_text(encoding="utf-8")
    assert "./results/ai-chat-panel.js" not in index_source
    assert "initAiChatPanel" not in index_source
    for shared_drawer_only_token in ("copy-payload", "copy-message", "redo-message", "ai-chat-icon-btn"):
        assert shared_drawer_only_token not in index_source


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
    assert "Re-run the selected candidate to create a persisted completed run before comparing it against the baseline run inline." in source
    assert "Loading persisted compare evidence for baseline" in source
    assert "Persisted compare evidence is unavailable:" in source
    assert "Decision evidence is grounded in persisted run summaries, request snapshots, and version artifacts only." in source


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
    assert "Re-run the selected candidate to create a persisted completed run before comparing it against the baseline run." in source
    assert "Loading persisted compare evidence for the baseline run and selected candidate..." in source
    assert "Persisted compare evidence is unavailable for the baseline run and selected candidate:" in source
    assert "Loading persisted compare evidence for the selected runs..." in source
    assert "Persisted compare evidence is unavailable for the selected runs:" in source
    assert "Decision evidence is grounded in persisted run summaries, request snapshots, and version artifacts only. Delta is right minus left." in source


def test_decision_renderer_exposes_diff_pair_and_diagnosis_sections():
    source = DECISION_RENDERER.read_text(encoding="utf-8")

    assert "Version Diff" in source
    assert "Decision Metrics" in source
    assert "Pair Delta" in source
    assert "Diagnosis Delta" in source
    assert "Action Type:" in source
    assert "Rule:" in source
    assert "Improved Pairs:" in source
    assert "Regressed Pairs:" in source
    assert "compare-diff-table" in source
    assert "compare-pairs-table" in source
    assert "compare-diagnosis-grid" in source
    assert "compare-cell-note" in source
    assert "decision-badge--" in source
