import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SHARED_DRAWER = ROOT / "web" / "static" / "js" / "components" / "ai-chat-panel.js"
SHARED_DRAWER_CSS = ROOT / "web" / "static" / "css" / "components" / "ai-chat-panel.css"
LEGACY_PANEL = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "ai-chat-panel.js"
API_CLIENT = ROOT / "web" / "static" / "js" / "core" / "api.js"
STATE = ROOT / "web" / "static" / "js" / "core" / "state.js"
BACKTESTING_INDEX = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "index.js"
BACKTESTING_HTML = ROOT / "web" / "templates" / "pages" / "backtesting" / "backtesting.html"
BACKTESTING_WORKFLOW_DOC = ROOT / "BACKTESTING_WORKFLOW.md"
BROWSER_SMOKE_DOC = ROOT / "BROWSER_SMOKE.md"
PROPOSAL_WORKFLOW = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "proposal-workflow.js"
COMPARE_PANEL = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "compare" / "compare-panel.js"
RESULTS_CONTROLLER = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "results-controller.js"
CANDIDATE_SELECTION_STATE = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "compare" / "candidate-selection-state.js"
DECISION_RENDERER = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "compare" / "decision-ready-renderer.js"
HISTORY_PANEL = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "history" / "history-panel.js"
PERSISTED_VERSIONS_STORE = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "persisted-versions-store.js"
MODAL_COMPONENT = ROOT / "web" / "static" / "js" / "components" / "modal.js"
STRATEGY_PANEL = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "setup" / "strategy-panel.js"
OPTIONS_LOADER = ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "setup" / "options-loader.js"
OPTIMIZER_INDEX = ROOT / "web" / "static" / "js" / "pages" / "optimizer" / "index.js"
PATHS_SETTINGS = ROOT / "web" / "static" / "js" / "pages" / "settings" / "paths-settings.js"
SETTINGS_TEMPLATE = ROOT / "web" / "templates" / "pages" / "settings" / "index.html"


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
    assert "Candidate creation requires a completed diagnosed run." in source
    assert "describeCandidateCreationState" in source
    assert "Use this drawer to explain diagnosed runs, regenerate replies, copy returned parameters or code, and create a versioned candidate from those payloads once run context is ready." in source
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


def test_proposal_workflow_uses_selected_candidate_state_decision_notes_and_decision_ready_compare():
    source = PROPOSAL_WORKFLOW.read_text(encoding="utf-8")

    assert 'import { closeModal, openModal } from "../../../components/modal.js";' in source
    assert 'import {' in source and 'subscribePersistedVersions,' in source
    assert "openDecisionNoteDialog" in source
    assert "Decision note" in source
    assert "Promotion Mode" in source
    assert "Accept as current" in source
    assert "Promote as new strategy" in source
    assert "Promote as new strategy variant" in source
    assert "Primary Issues" in source
    assert "Actionable now" in source
    assert "Diagnostic only" in source
    assert "Current live target is" in source
    assert "New strategy name" in source
    assert "promotion_mode" in source
    assert "new_strategy_name" in source
    assert "loadOptions();" in source
    assert "switchBacktestStrategy" in source
    assert "switchBacktestStrategy(response.new_strategy_name)" in source
    assert source.count("Decision note") >= 2
    assert "proposal-audit-note" in source
    assert 'data-role="selected-candidate"' in source
    assert "Selected Candidate" in source
    assert "renderDecisionReadyCompare(compareState.data" in source
    assert "setSelectedCandidateVersionId(response.candidate_version_id);" in source
    assert 'onState("backtest.selectedCandidateVersionId", () => {' in source
    assert "ensureSelectedCandidateVersion(versionsState.versions, currentBaselineRunId())" in source
    assert "Candidate Compare" in source
    assert "Proposal Workflow" in source
    assert "Start here after reviewing diagnosis." in source
    assert "Actionable now" in source
    assert "Diagnostic-only items explain the run but do not stage a candidate path by themselves." in source
    assert "Re-run the selected candidate to create a persisted completed run before comparing it against the baseline run inline." in source
    assert "Loading persisted compare evidence for baseline" in source
    assert "Persisted compare evidence is unavailable:" in source
    assert "Use this evidence before choosing Accept as current strategy or Promote as new strategy variant." in source


def test_compare_panel_is_workflow_aware_and_uses_shared_versions_store():
    source = COMPARE_PANEL.read_text(encoding="utf-8")

    assert "workflowModeActive" in source
    assert "Baseline" in source
    assert "Selected Candidate" in source
    assert "renderDecisionReadyCompare(lastComparison" in source
    assert "getWorkflowCandidateVersions(versionsState.versions, workflowBaselineRunId())" in source
    assert "initPersistedVersionsStore" in source
    assert "subscribePersistedVersions(handleVersionsSnapshot)" in source
    assert 'onState("backtest.selectedCandidateVersionId", () => {' in source
    assert "Left run" in source
    assert "Right run" in source
    assert "No persisted candidates are linked to the current baseline run yet. Create one from Proposal Workflow first." in source
    assert "workflowHasLinkedCandidates" in source
    assert 'versionsState.status !== "ready"' in source
    assert "Re-run the selected candidate to create a persisted completed run before comparing it against the baseline run." in source
    assert "Loading persisted compare evidence for the baseline run and selected candidate..." in source
    assert "Persisted compare evidence is unavailable for the baseline run and selected candidate:" in source
    assert "Use Compare after rerun and before any version decision." in source
    assert "Loading persisted compare evidence for the selected runs..." in source
    assert "Persisted compare evidence is unavailable for the selected runs:" in source
    assert "No persisted completed runs with saved summary artifacts are available to compare yet. Run a baseline backtest or candidate rerun first." in source
    assert "Decision evidence is grounded in persisted run summaries, request snapshots, and version artifacts only. Delta is right minus left." in source


def test_decision_renderer_exposes_summary_first_diff_pair_and_diagnosis_sections():
    source = DECISION_RENDERER.read_text(encoding="utf-8")

    assert "Decision Snapshot" in source
    assert "compare-snapshot-grid" in source
    assert "compare-section-details" in source
    assert "compare-version-diff-grid" in source
    assert "compare-param-groups" in source
    assert "compare-code-preview" in source
    assert "preview_truncated" in source
    assert "Version Diff" in source
    assert "Decision Metrics" in source
    assert "Pair Delta" in source
    assert "Diagnosis Delta" in source
    assert "Action Type:" in source
    assert "Rule:" in source
    assert "Improved Pairs:" in source
    assert "Regressed Pairs:" in source
    assert "compare-pairs-table" in source
    assert "compare-diagnosis-grid" in source
    assert "compare-cell-note" in source
    assert "decision-badge--" in source


def test_strategy_panel_owns_programmatic_strategy_switching():
    source = STRATEGY_PANEL.read_text(encoding="utf-8")

    assert "function applyStrategySelection(strategyName)" in source
    assert "export function switchBacktestStrategy(strategyName)" in source
    assert 'setState("backtest.strategy", next);' in source
    assert 'persistBacktestConfig?.((prev) => ({ ...prev, strategy: next }));' in source
    assert 'Array.from(select.options).some((option) => option.value === next)' in source


def test_history_panel_is_hybrid_and_uses_shared_versions_store():
    source = HISTORY_PANEL.read_text(encoding="utf-8")
    store_source = PERSISTED_VERSIONS_STORE.read_text(encoding="utf-8")
    modal_source = MODAL_COMPONENT.read_text(encoding="utf-8")

    assert "History Overview" in source
    assert "Version Decisions" in source
    assert '["all", "All"]' in source
    assert '["runs", "Runs"]' in source
    assert '["decisions", "Decisions"]' in source
    assert "history-decision-card" in source
    assert "history-audit-row" in source
    assert "initPersistedVersionsStore" in source
    assert "subscribePersistedVersions" in source
    assert "latestAuditNote" in source
    assert "promoted_as_new_strategy" in source
    assert "Current Live Target" in source
    assert "Pinned active version is the current live target." in source
    assert "latest note snippet" in source
    assert "Run a baseline backtest or candidate rerun first." in source

    assert "activeVersionId" in store_source
    assert "api.versions.listVersions(strategy, true)" in store_source
    assert "export async function refreshPersistedVersions" in store_source

    assert "onClose" in modal_source
    assert "activeOnClose" in modal_source


def test_results_controller_surfaces_overlay_fields_and_primary_issue_copy() -> None:
    source = RESULTS_CONTROLLER.read_text(encoding="utf-8")

    for token in (
        "Workflow Guide",
        "Configure Strategy",
        "Run Backtest",
        "Review Diagnosis",
        "Create Candidate",
        "Re-run & Compare",
        "Decide Version",
        "Actionable now",
        "Diagnostic only",
        "Promote as new strategy",
        "open-compare",
        "open-history",
        "Primary Issues",
        "Recommended next step",
        "Confidence",
        "Code change summary",
        "Advisory only. Deterministic diagnosis remains the source of truth for version decisions.",
    ):
        assert token in source


def test_summary_workflow_shell_and_docs_exist() -> None:
    html = BACKTESTING_HTML.read_text(encoding="utf-8")
    workflow_doc = BACKTESTING_WORKFLOW_DOC.read_text(encoding="utf-8")
    smoke_doc = BROWSER_SMOKE_DOC.read_text(encoding="utf-8")

    assert 'id="summary-workflow-guide"' in html
    assert "Workflow Guide" in workflow_doc
    assert "Promote as new strategy variant" in workflow_doc
    assert "Playwright CLI" in smoke_doc
    assert "output/playwright/" in smoke_doc
    assert "Promote as new strategy variant" in smoke_doc


def test_shared_drawer_explicitly_selects_the_created_candidate_version():
    source = SHARED_DRAWER.read_text(encoding="utf-8")

    assert 'import { setSelectedCandidateVersionId } from "../pages/backtesting/compare/candidate-selection-state.js";' in source
    assert 'setSelectedCandidateVersionId(response.candidate_version_id);' in source


def test_candidate_selection_state_filters_workflow_choices_to_pending_candidates_only():
    source = CANDIDATE_SELECTION_STATE.read_text(encoding="utf-8")

    assert "function isPendingWorkflowCandidate(version)" in source
    assert 'String(version?.status || "").toLowerCase() === "candidate"' in source
    assert '.filter((version) => version?.source_ref === sourceRef && isPendingWorkflowCandidate(version))' in source


def test_ai_apply_reruns_keep_the_workflow_pinned_to_the_baseline_diagnosis():
    run_controller = (ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "run" / "run-controller.js").read_text(encoding="utf-8")
    results_controller = (ROOT / "web" / "static" / "js" / "pages" / "backtesting" / "results" / "results-controller.js").read_text(encoding="utf-8")

    assert "let _currentRunMeta = { trigger_source: null, version_id: null, strategy: null };" in run_controller
    assert "function setCurrentRunMeta(meta = null)" in run_controller
    assert "function currentRunEventMeta(status, exitCode, error)" in run_controller
    assert "emit(EVENTS.BACKTEST_COMPLETE, currentRunEventMeta(s, exitCode, error));" in run_controller
    assert 'triggerSource === "ai_apply"' in results_controller
    assert "function shouldPreserveWorkflowBaseline(event)" in results_controller
    assert "if (shouldPreserveWorkflowBaseline(event))" in results_controller


def test_options_loader_normalizes_and_resolves_dropdown_defaults():
    source = OPTIONS_LOADER.read_text(encoding="utf-8")

    assert "Promise.allSettled" in source
    assert "persistBacktestSelections" in source
    assert "applyResolvedSelection" in source
    assert "persistBacktestSelectionRepairs" in source
    assert "No strategies found" in source
    assert "No timeframes available" in source
    assert "result.settings.default_timeframe" in source


def test_backtesting_and_optimizer_share_the_same_dropdown_loader_contract():
    backtesting_source = BACKTESTING_INDEX.read_text(encoding="utf-8")
    optimizer_source = OPTIMIZER_INDEX.read_text(encoding="utf-8")

    assert 'const optionsResult = await loadOptions({ persistBacktestSelections: true });' in backtesting_source
    assert 'setState("backtest.timeframe", optionsResult.selected.timeframe || "");' in backtesting_source
    assert 'setState("backtest.exchange", optionsResult.selected.exchange || "");' in backtesting_source
    assert 'document.getElementById("select-exchange")' in backtesting_source

    assert 'import { loadOptions } from "../backtesting/setup/options-loader.js";' in optimizer_source
    assert 'exchangeSelectId: null,' in optimizer_source
    assert "api.backtest.options" not in optimizer_source


def test_settings_path_ux_accepts_explicit_freqtrade_paths_without_bad_derivations():
    source = PATHS_SETTINGS.read_text(encoding="utf-8")
    template = SETTINGS_TEMPLATE.read_text(encoding="utf-8")

    assert "function inferFreqtradeRoot(rawPath)" in source
    assert "freqtrade(?:\\.exe)?" in source
    assert 'tail === "scripts" || tail === "bin"' in source
    assert 'tail === ".venv" || tail === "venv"' in source
    assert 'Resolved executable: ${resolvedPath}' in source
    assert 'joinDerivedPath(inferredRoot, parts)' in source
    assert 'if (el && !el.value.trim())' in source

    assert "Freqtrade Path" in template
    assert "/home/user/freqtrade or /home/user/freqtrade/.venv/bin/freqtrade" in template
