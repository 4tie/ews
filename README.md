# 4tie

4tie is a controlled AI-assisted Freqtrade strategy improvement workbench.

The app is built around one non-negotiable workflow:

1. choose a strategy and config
2. run a backtest
3. load and explain the result
4. stage a parameter or code candidate as a new version
5. rerun from that exact version
6. compare baseline vs candidate
7. explicitly accept, reject, or roll back

It is not an autonomous strategy rewriter. AI can explain, diagnose, and stage candidates, but it cannot silently promote live changes.

## What exists now

### Core app surface
- FastAPI app with Jinja pages served from `app/main.py`
- root redirects to `/backtesting`
- API docs available at `/api/docs`
- three main pages:
  - `/backtesting` - primary product surface
  - `/optimizer` - legacy/partial optimizer page
  - `/settings` - app and AI configuration

### Backtesting workflow
- choose strategy, timeframe, exchange, timerange, and pairs
- validate OHLCV coverage before running
- download missing candles through the same UI
- run backtests with live log streaming and stop support
- persist each run under `data/backtest_runs/<run_id>/run_meta.json`
- link every run to the exact `version_id` used
- ingest Freqtrade result artifacts into normalized summary data
- compute diagnosis flags, ranked issues, parameter hints, and deterministic proposal actions
- create proposal candidates from:
  - deterministic diagnosis actions
  - ranked issues
  - parameter hints
  - AI parameter suggestions
  - AI chat drafts
- rerun candidates from isolated workspaces
- compare baseline vs candidate with:
  - metrics deltas
  - request snapshot diff
  - version diff
  - parameter diff rows
  - code diff summary
  - pair deltas
  - diagnosis delta
- explicitly accept as current strategy, reject, roll back, or promote as a new strategy variant

### Versioning and safety
- all mutations flow through `app/services/mutation_service.py`
- candidate creation does not write live strategy files
- live writes only happen through accept or rollback
- promotion-as-new-strategy creates a new lineage, then promotes that lineage
- rollback restores the exact effective artifacts from version lineage
- reruns use `data/backtest_runs/<run_id>/workspace/` and do not touch live `user_data`

### AI workflow
- shared persistent chat workflow with per-strategy threads and job streaming
- run-scoped context for AI replies and candidate staging
- provider routing supports `ollama`, `openrouter`, `huggingface`, and `openai`
- settings UI currently has first-class discovery only for Ollama; other providers are configured through model and env settings

### AI parameter suggestions contract (Run Intelligence Package)

The run-diagnosis AI overlay is fed a deterministic, structured **Run Intelligence Package** (no raw/chaotic summary dumps) and must return **strict JSON** only.

**Input (run intelligence package)**
- built from persisted run summary + deterministic diagnosis + version artifacts
- includes: `run_summary`, trimmed `trades`, trimmed `results_per_pair`, `diagnosis` (flags/issues/hints/actions), `parameter_snapshot`, `parameter_space`, `safe_keys`, `version_context`

**Output (v2 strict JSON, delta-based only)**
```json
{
  "summary": "...",
  "suggestions": [
    {
      "key": "buy_ma_gap",
      "direction": "increase",
      "delta": 2,
      "reason": "...",
      "evidence": ["overtrading"],
      "confidence": 0.72
    }
  ],
  "confidence": 0.66
}
```

**Hard-fail validator (before any candidate is staged)**
- `suggestions` must be a list of `1..5` items (if >5: reject, no auto-trim)
- `key` must be in `safe_keys`:
  - declared tunables parsed from strategy code (`IntParameter`, `DecimalParameter`, `CategoricalParameter`, `BooleanParameter`)
  - plus a small risk set: `stoploss`, `trailing_stop`, `trailing_stop_positive`, `trailing_stop_positive_offset`, `trailing_only_offset_is_reached`, `minimal_roi`
- delta suggestions apply only to numeric scalar keys (`int`/`float`); reject `bool`, `categorical`, and `roi_dict` in delta-mode
- range/step enforced when available (`min <= next_value <= max`, delta matches `step` with float epsilon)
- evidence tokens must come from the deterministic diagnosis rule allowlist (`flags/primary_flags/ranked_issues/parameter_hints[*].rule`)

**Suggestions → candidate snapshot + audit trail**
- proposal staging accepts `ProposalCandidateRequest.suggestions` (preferred) or legacy `parameters` (validated)
- backend applies deltas to a deep-copied `parameter_snapshot` and stages a new CANDIDATE version
- `source_context` records the exact applied changes (`applied_suggestions` with `current_value`/`next_value`, or `applied_parameters_patch`)
### Auto Optimize v1
- parameter-only beam-search optimizer anchored to a completed baseline run
- surfaced in the Backtesting summary panel
- persists optimizer runs, nodes, finalists, near misses, and event streams
- finalist versions can be selected directly as workflow candidates

## Canonical ownership points

- `app/main.py` - app entrypoint, route mounting, reload exclusions
- `app/freqtrade/runtime.py` - backtest workflow orchestration
- `app/freqtrade/cli_service.py` - Freqtrade command prep, result paths, isolated version workspaces
- `app/services/results_service.py` - ingestion, normalized summaries, compare payloads
- `app/services/results/diagnosis_service.py` - diagnosis facts, ranked issues, deterministic actions
- `app/services/results/strategy_intelligence_apply_service.py` - proposal candidate creation
- `app/services/mutation_service.py` - version lifecycle, compare evidence, live promotion, rollback
- `app/services/ai_chat/persistent_chat_service.py` - persistent AI chat threads and jobs

## Storage layout

App-owned state lives under `data/`:

- `data/settings/` - saved app settings
- `data/saved_configs/` - saved backtest configs
- `data/backtest_runs/<run_id>/` - run metadata, logs, workspace, normalized results
- `data/download_runs/<download_id>/` - download job metadata and logs
- `data/optimizer_runs/<optimizer_run_id>/` - auto-optimize records, nodes, events, checkpoints
- `data/versions/<strategy_name>/` - version records and active pointer
- `data/ai_chat_threads/` - per-strategy chat history
- `data/ai_chat_jobs/` - background AI job state and timeline events

Live Freqtrade artifacts remain under `user_data/` and are only updated through explicit promotion paths.

## Start locally

Use the repo-owned entrypoint:

```powershell
python app\main.py
```

Then open:

- `http://127.0.0.1:5000/backtesting`
- `http://127.0.0.1:5000/settings`
- `http://127.0.0.1:5000/api/docs`

Do not document raw `uvicorn --reload` as the primary startup path. `app/main.py` owns the reload exclusions required for workflow-generated files.

## What still needs to be added to call the app complete

### 1. Converge optimizer surfaces
- `Auto Optimize v1` on `/backtesting` is the implemented optimizer workflow
- the legacy `/optimizer` page still depends on `app/services/autotune/iterative_optimizer.py`, which is mostly a stub
- `web/static/js/pages/optimizer/optimizer.js` still has a frontend-only stop flow and no real backend stop/pause control
- `PersistenceService.rollback()` still returns checkpoint data without reactivating anything

Decision required: either finish the legacy optimizer path end to end, or retire it and keep `/backtesting` as the only optimizer workflow.

### 2. Reduce parallel AI entrypoints
- `/api/backtest/runs/{run_id}/proposal-candidates` is the run-scoped workflow-safe mutation path
- `/api/ai/chat/*` is the persistent assistant workflow
- `/api/ai/evolution/*` still exists as a lower-level analysis/apply surface

To finish the product cleanly, the repo should define which of these is canonical and treat the others as adapters, not competing workflows.

### 3. Expand browser-level regression coverage
- backend and contract tests cover most workflow rules already
- the remaining gap is richer end-to-end browser proof for accept, reject, rollback, promote-as-new-strategy, and auto-optimize finalist selection

### 4. Finish final UX polish only after the above
- richer compare diff rendering
- clearer audit/history surfacing
- optional export/reporting polish
- provider-specific settings UX beyond Ollama discovery

## Current reality in one sentence

The backtesting/versioning/compare contract is already the real product; the main work left is removing or finishing legacy parallel surfaces so the app has one clear, complete path.

