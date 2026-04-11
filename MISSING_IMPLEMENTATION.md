# Missing Implementation Guide

## Completed ✓
- `_freqtrade_subprocess_env()` — Now removes `FT_FORCE_THREADED_RESOLVER` and returns env dict
- Backend API routes for backtest, optimizer, settings, ai_chat, evolution, versions
- Frontend template response signature fixed for Starlette 0.36+
- Header config buttons (Load/Save) with modal picker
- Engine abstraction layer (FreqtradeEngine, resolver)
- Data validation endpoint with coverage checking
- Backtest run watcher threads and process management
- Download data subprocess management

---

## Critical Missing Pieces

### 1. **Frontend JavaScript Modules** (High Priority)
These modules are imported but may not be fully implemented:

#### Setup Panels
- `setup/options-loader.js` — Load strategies, timeframes, exchanges from API
- `setup/strategy-panel.js` — Handle strategy selection, emit state changes
- `setup/time-panel.js` — Date range picker with presets (7d, 30d, 90d, YTD)
- `setup/pairs-panel.js` — Add/remove pairs, tag list UI
- `setup/json-config-parser.js` — Parse JSON config paste, extract pairs

#### Run Controllers
- `run/run-controller.js` — Wire "Run Backtest" button, handle BacktestRunRequest
- `run/log-panel.js` — Stream logs via SSE from `/api/backtest/runs/{run_id}/logs/stream`
- `run/data-download.js` — Wire "Download Data" button, stream download logs
- `run/data-validator.js` — Wire "Validate Data" button, display validation results

#### Results Display
- `trades/table.js` — Render trades table from backtest results
- `trades/pair-summary.js` — Render per-pair summary table
- `components/command-preview.js` — Update command preview as form changes
- `components/pair-input.js` — Pair input field with validation

#### Core Utilities
- `core/utils.js` — `$$()` selector utility, DOM helpers
- `components/loading-state.js` — Show/hide loading spinners
- `components/toast.js` — Toast notifications (already referenced, may need completion)

### 2. **Backend Services** (High Priority)

#### Results Service (`app/services/results_service.py`)
- `ingest_backtest_run(run_record)` — Parse backtest result ZIP, extract summary/trades
- `load_run_summary_state(run)` — Load summary JSON with error handling
- `extract_run_summary_block(summary, strategy)` — Extract strategy-specific block
- `_normalize_summary_metrics(summary, strategy)` — Normalize metrics for display
- `summarize_backtest_run(run)` — Return run summary for list/detail views
- `compare_backtest_runs(left_run, right_run)` — Compare two runs side-by-side

#### Diagnosis Service (`app/services/results/diagnosis_service.py`)
- `empty_diagnosis()` — Return empty diagnosis template
- `diagnose_run(run_record, summary_metrics, ...)` — Analyze run for issues/opportunities

#### Strategy Intelligence Service (`app/services/results/strategy_intelligence_service.py`)
- `analyze_run_diagnosis_overlay(strategy_name, diagnosis, ...)` — AI analysis of diagnosis
- `analyze_strategy(strategy_name, strategy_code, backtest_results, ...)` — AI strategy analysis
- `analyze_metrics(metrics, context)` — AI metrics analysis

#### Strategy Intelligence Apply Service (`app/services/results/strategy_intelligence_apply_service.py`)
- `create_proposal_candidate_from_diagnosis(...)` — Create version candidate from AI suggestions
- `apply_strategy_recommendations(...)` — Apply recommendations to strategy

#### Validation Service (`app/services/validation_service.py`)
- `validate_timeframe(timeframe)` — Check if timeframe is valid
- `validate_timerange(timerange)` — Parse and validate timerange string
- `validate_pair(pair)` — Check pair format (BASE/QUOTE)

#### Mutation Service (`app/services/mutation_service.py`)
- `create_mutation(request)` — Create a new version mutation
- `accept_version(version_id, notes)` — Accept/promote a version
- `get_version_by_id(version_id)` — Load version by ID
- `get_active_version(strategy_name)` — Get currently active version
- `get_version(strategy_name, version_id)` — Load version for strategy
- `list_versions(strategy_name, include_archived)` — List all versions
- `link_backtest(version_id, run_id, profit_pct)` — Link backtest to version
- `resolve_effective_artifacts(version_id)` — Get code/parameters snapshot
- `rollback_version(target_version_id, reason)` — Rollback to older version

#### Persistence Service (`app/services/persistence_service.py`)
- `save_backtest_run(run_id, data)` — Persist run metadata
- `load_backtest_run(run_id)` — Load run metadata
- `list_backtest_runs()` — List all run metadata
- `save_download_run(download_id, data)` — Persist download metadata
- `load_download_run(download_id)` — Load download metadata

### 3. **Utility Modules** (Medium Priority)

#### `app/utils/datetime_utils.py`
- `now_iso()` — Return current time in ISO format
- `timestamp_slug()` — Generate timestamp-based slug
- `parse_timerange(timerange_str)` — Parse freqtrade timerange format

#### `app/utils/paths.py`
- `BASE_DIR` — Project root directory
- `strategy_results_dir(strategy)` — Path to strategy results
- `backtest_runs_dir()` — Path to backtest run metadata
- `download_runs_dir()` — Path to download run metadata
- `user_data_results_dir()` — Path to user_data/backtest_results
- `live_strategy_file(strategy_name, user_data_path)` — Path to live strategy file
- `strategy_config_file(strategy_name, user_data_path)` — Path to strategy config
- `default_freqtrade_config_path(user_data_path)` — Default config.json path
- `resolve_safe(base, *parts)` — Safe path joining with validation

#### `app/utils/json_io.py`
- `read_json(path, fallback)` — Read JSON file with fallback
- `write_json(path, data)` — Write JSON file with directory creation
- `list_json_files(directory)` — List JSON files in directory

#### `app/utils/command_builder.py`
- `build_backtest_command(...)` — Build freqtrade backtest command list
- `build_download_command(...)` — Build freqtrade download-data command list
- `command_to_string(cmd)` — Convert command list to shell string

### 4. **Models** (Medium Priority)

#### `app/models/backtest_models.py`
- `BacktestRunRequest` — Request model for backtest runs
- `BacktestRunRecord` — Persistent run record model
- `BacktestRunStatus` — Enum for run status
- `ConfigSaveRequest` — Request model for saving configs
- `ProposalCandidateRequest` — Request model for proposal candidates

#### `app/models/optimizer_models.py`
- `OptimizerRunRequest` — Request model for optimizer runs
- `ChangeType` — Enum for mutation types (INITIAL, EVOLUTION, etc.)
- `MutationRequest` — Request model for creating mutations
- `StrategyVersion` — Version record model
- `AcceptRequest`, `RollbackRequest` — Version control request models

#### `app/models/settings_models.py`
- `AppSettings` — Application settings model

### 5. **Frontend HTML Templates** (Low Priority - Structure exists)
- `web/templates/pages/optimizer/index.html` — Optimizer page
- `web/templates/pages/settings/index.html` — Settings page
- `web/templates/partials/modal_container.html` — Modal overlay
- `web/templates/partials/toast_container.html` — Toast notifications

### 6. **Frontend CSS** (Low Priority - Structure exists)
- `web/static/css/pages/backtesting.css` — Backtesting page styles
- `web/static/css/components/` — Component styles

---

## Implementation Priority

### Phase 1 (Critical - App won't run)
1. Complete `app/utils/` modules (paths, datetime_utils, json_io, command_builder)
2. Complete `app/models/` modules (backtest_models, optimizer_models, settings_models)
3. Complete `app/services/persistence_service.py`
4. Complete `app/services/validation_service.py`

### Phase 2 (High - Core functionality)
1. Complete `app/services/results_service.py`
2. Complete `app/services/mutation_service.py`
3. Complete frontend JS modules (setup, run, results)
4. Wire up backtest run flow end-to-end

### Phase 3 (Medium - AI features)
1. Complete diagnosis service
2. Complete strategy intelligence services
3. Wire up AI analysis endpoints

### Phase 4 (Low - Polish)
1. Complete optimizer service
2. Complete evolution/versions endpoints
3. Add missing CSS/templates

---

## Quick Start Checklist

- [ ] Implement `app/utils/paths.py` with all path helpers
- [ ] Implement `app/utils/datetime_utils.py` with time utilities
- [ ] Implement `app/utils/json_io.py` with JSON helpers
- [ ] Implement `app/models/backtest_models.py` with Pydantic models
- [ ] Implement `app/services/persistence_service.py` for run metadata
- [ ] Implement `app/services/validation_service.py` for data validation
- [ ] Implement `app/services/results_service.py` for result ingestion
- [ ] Create `web/static/js/core/utils.js` with DOM helpers
- [ ] Create `web/static/js/pages/backtesting/setup/options-loader.js`
- [ ] Create `web/static/js/pages/backtesting/run/run-controller.js`
- [ ] Test backtest run flow: UI → API → subprocess → results ingestion

---

## Notes

- The app uses a **plugin architecture** with `BacktestEngine` abstraction (currently only FreqtradeEngine)
- **Version control** is built-in via `mutation_service` for strategy evolution tracking
- **AI integration** is designed for two-mode output (parameters-only or code patches)
- **Process management** uses daemon threads to watch subprocess completion
- **SSE streaming** for live log output during backtest/download runs
- **Modular frontend** with event bus (`events.js`) and state store (`state.js`)
