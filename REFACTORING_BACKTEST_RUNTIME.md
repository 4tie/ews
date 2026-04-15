# Backtest Runtime Refactoring - Decomposition Complete

## Overview
Successfully decomposed `app/freqtrade/runtime.py` into 6 focused modules while maintaining full backward compatibility through a compatibility facade.

## New Module Structure

### 1. `backtest_process.py` (Foundational)
**Responsibility**: Run record lifecycle, process monitoring, watcher registry

**Key Functions**:
- `_save_run_record()` - Persist run metadata
- `_load_run_record()` - Load and reconcile stale runs
- `_list_freqtrade_runs()` - List runs by strategy
- `_process_matches_run_record()` - Verify process is still running
- `_resolve_process_exit_code()` - Get process exit code
- `_terminate_process_tree()` - Kill process and children
- `_mark_failed_run()` - Mark run as failed
- `_mark_stopped_run()` - Mark run as stopped
- `_finalize_successful_backtest_run()` - Finalize and ingest results
- `_reconcile_stale_backtest_run()` - Reconcile stale RUNNING runs
- `_watch_backtest_process()` - Background watcher thread
- `_start_backtest_watcher()` - Start watcher thread
- `stop_backtest_run()` - Public API to stop a run

**Dependencies**: 
- `ResultsService` (lazy import to avoid cycles)
- `mutation_service`
- `persistence`

### 2. `backtest_runner.py`
**Responsibility**: Strategy loading, version resolution, backtest launch

**Key Functions**:
- `load_live_strategy_code()` - Load strategy source from disk
- `load_live_strategy_parameters()` - Load strategy config
- `_bootstrap_initial_version()` - Create initial version from live strategy
- `_resolve_version_for_launch()` - Resolve version for backtest
- `_build_request_snapshot()` - Build request metadata
- `_resolve_engine()` - Resolve engine from settings
- `get_options()` - Return available strategies/timeframes/exchanges
- `run_backtest()` - Public API to launch backtest

**Dependencies**:
- `backtest_process` (for `_save_run_record`, `_start_backtest_watcher`)
- `backtest_stream` (for `_derive_backtest_progress`)
- `mutation_service`
- `config_svc`

### 3. `backtest_stream.py`
**Responsibility**: Log streaming, progress tracking, SSE generation

**Key Functions**:
- `_derive_backtest_progress()` - Parse progress from logs
- `_terminal_backtest_progress()` - Get terminal status progress
- `_sse()` - Format SSE payload
- `stream_log_response()` - Generic SSE stream generator
- `stream_backtest_logs()` - Public API for backtest log streaming

**Dependencies**:
- `backtest_process` (for `_load_run_record`, `_tail_log_lines`)
- `backtest_results` (lazy import for `_summarize_run_record`)

### 4. `backtest_results.py`
**Responsibility**: Results orchestration, summary loading, comparison

**Key Functions**:
- `_summarize_run_record()` - Summarize run with progress
- `list_backtest_runs()` - List runs with summaries
- `get_backtest_run()` - Get single run summary
- `compare_backtest_runs()` - Compare two runs
- `get_summary()` - Get latest summary for strategy
- `get_trades()` - Get trades from latest summary

**Dependencies**:
- `backtest_process` (for `_load_run_record`, `_list_freqtrade_runs`)
- `backtest_stream` (for `_derive_backtest_progress`)
- `results_svc`

### 5. `backtest_diagnosis.py`
**Responsibility**: Diagnosis status, AI payload defaults, diagnosis context

**Key Functions**:
- `_derive_diagnosis_status()` - Determine diagnosis readiness
- `_default_ai_payload()` - Create default AI payload
- `_resolve_linked_version_for_run()` - Resolve version for diagnosis
- `get_backtest_run_diagnosis()` - Public API for diagnosis

**Dependencies**:
- `backtest_process` (for `_load_run_record`)
- `diagnosis_service`
- `analyze_run_diagnosis_overlay`
- `results_svc`
- `mutation_service`

### 6. `proposal_service.py`
**Responsibility**: Proposal candidate creation and response building

**Key Functions**:
- `_build_proposal_candidate_response()` - Build response payload
- `create_backtest_run_proposal_candidate()` - Public API for candidate creation

**Dependencies**:
- `backtest_diagnosis` (for `_default_ai_payload`, `_resolve_linked_version_for_run`)
- `backtest_process` (for `_load_run_record`)
- `diagnosis_service`
- `analyze_run_diagnosis_overlay`
- `results_svc`

### 7. `runtime.py` (Compatibility Facade)
**Responsibility**: Re-export all public APIs, maintain backward compatibility

**Exports**:
- All backtest runner functions
- All backtest process functions
- All backtest stream functions
- All backtest results functions
- All backtest diagnosis functions
- All proposal service functions
- Download/config/validation functions (unchanged)
- Service singletons: `results_svc`, `config_svc`, `persistence`, `validation_svc`

**Non-backtest Functions** (remain in runtime.py):
- `download_data()` - Download candle data
- `stream_download_logs()` - Stream download logs
- `list_configs()` - List saved configs
- `save_config()` - Save config
- `load_config()` - Load config
- `delete_config()` - Delete config
- `validate_data()` - Validate pair/timeframe coverage

## Backward Compatibility

### Import Paths Unchanged
All existing imports continue to work:
```python
from app.freqtrade.runtime import (
    run_backtest,
    stop_backtest_run,
    stream_backtest_logs,
    get_backtest_run_diagnosis,
    create_backtest_run_proposal_candidate,
    _reconcile_stale_backtest_run,
    _watch_backtest_process,
    load_live_strategy_code,
    # ... etc
)
```

### Router Compatibility
All routes in `app/routers/backtest.py` continue to work without modification.

### Test Compatibility
All existing tests continue to pass:
- `test_backtest_run_control.py`
- `test_backtest_run_diagnosis.py`
- `test_ai_chat_candidate_contract.py`
- `test_backtest_history_compare.py`
- `test_backtest_workflow_loop.py`
- `test_version_promotion_contract.py`
- `test_optimizer_auto_optimize_engine.py`

## Dependency Graph

```
backtest_process.py (foundational)
├── backtest_runner.py
├── backtest_stream.py
├── backtest_results.py
├── backtest_diagnosis.py
└── proposal_service.py

runtime.py (facade)
└── re-exports all above + download/config/validation
```

## Circular Dependency Avoidance

**Strategy**: Lazy imports in functions that would create cycles

1. `backtest_process._finalize_successful_backtest_run()`:
   - Lazy imports `ResultsService` and `mutation_service`

2. `backtest_stream.stream_backtest_logs()`:
   - Lazy imports `_summarize_run_record` from `backtest_results`

3. `proposal_service.create_backtest_run_proposal_candidate()`:
   - Lazy imports `create_proposal_candidate_from_diagnosis`

4. `runtime.py`:
   - Lazy imports `create_proposal_candidate_from_diagnosis` via `_get_create_proposal_candidate_fn()`

## Testing Strategy

### Regression Tests (Existing)
All existing tests pass without modification because:
- Public API signatures unchanged
- Import paths unchanged
- Behavior identical

### New Regression Tests (Recommended)
1. **Test facade re-exports**: Verify `runtime.py` correctly re-exports all functions
2. **Test progress streaming**: Verify progress payload unchanged after move to `backtest_stream.py`
3. **Test proposal candidate**: Verify baseline/version linkage unchanged after move to `proposal_service.py`

## Future Phases

### Phase 2: Download Data Refactoring
- Extract `download_data()` and `stream_download_logs()` to `download_service.py`
- Extract config CRUD to `config_service.py` (or extend existing `ConfigService`)
- Extract `validate_data()` to `validation_service.py` (or extend existing `ValidationService`)

### Phase 3: Optimizer Integration
- Update `app/services/autotune/auto_optimize_service.py` to import from new modules
- Verify optimizer tests still pass

### Phase 4: Router Cleanup
- Update `app/routers/backtest.py` to import from specific modules (optional)
- Keep `runtime.py` as facade for backward compatibility

## Files Modified

### Created
- `app/freqtrade/backtest_process.py` (280 lines)
- `app/freqtrade/backtest_runner.py` (240 lines)
- `app/freqtrade/backtest_stream.py` (160 lines)
- `app/freqtrade/backtest_results.py` (80 lines)
- `app/freqtrade/backtest_diagnosis.py` (130 lines)
- `app/freqtrade/proposal_service.py` (150 lines)

### Modified
- `app/freqtrade/runtime.py` (refactored to facade, ~350 lines)

### Unchanged
- All routers
- All services
- All models
- All tests

## Verification Checklist

- [x] All 6 new modules created
- [x] `runtime.py` refactored to facade
- [x] All public APIs re-exported
- [x] Circular dependencies avoided
- [x] Backward compatibility maintained
- [x] No changes to routers or tests required
- [x] Documentation updated

## Summary

The refactoring successfully decomposes `runtime.py` from a 1000+ line monolith into 6 focused, single-responsibility modules while maintaining 100% backward compatibility. The facade pattern ensures existing code continues to work without modification, enabling gradual migration to direct imports from specific modules in future phases.
