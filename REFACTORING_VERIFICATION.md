# Backtest Runtime Refactoring - Verification Guide

## Quick Verification Steps

### 1. Verify All New Modules Exist
```bash
ls -la app/freqtrade/backtest_*.py
ls -la app/freqtrade/proposal_service.py
```

Expected output:
- `app/freqtrade/backtest_process.py`
- `app/freqtrade/backtest_runner.py`
- `app/freqtrade/backtest_stream.py`
- `app/freqtrade/backtest_results.py`
- `app/freqtrade/backtest_diagnosis.py`
- `app/freqtrade/proposal_service.py`

### 2. Verify Backward Compatibility - Import Test
```python
# This should work without modification
from app.freqtrade.runtime import (
    run_backtest,
    stop_backtest_run,
    stream_backtest_logs,
    get_backtest_run_diagnosis,
    create_backtest_run_proposal_candidate,
    _reconcile_stale_backtest_run,
    _watch_backtest_process,
    _is_terminal_status,
    _derive_backtest_progress,
    load_live_strategy_code,
    load_live_strategy_parameters,
    _load_run_record,
    _start_backtest_watcher,
    _summarize_run_record,
    _default_ai_payload,
    _resolve_linked_version_for_run,
    _derive_diagnosis_status,
    download_data,
    stream_download_logs,
    list_configs,
    save_config,
    load_config,
    delete_config,
    validate_data,
    results_svc,
    config_svc,
    persistence,
    validation_svc,
    analyze_run_diagnosis_overlay,
)
```

### 3. Run Existing Tests
```bash
# All these should pass without modification
pytest test_backtest_run_control.py -v
pytest test_backtest_run_diagnosis.py -v
pytest test_ai_chat_candidate_contract.py -v
pytest test_backtest_history_compare.py -v
pytest test_backtest_workflow_loop.py -v
pytest test_version_promotion_contract.py -v
pytest test_optimizer_auto_optimize_engine.py -v
```

### 4. Verify Router Compatibility
```bash
# Start the app
python app/main.py

# Test backtest endpoints (should work without modification)
curl http://127.0.0.1:5000/api/backtest/options
curl http://127.0.0.1:5000/api/backtest/runs
```

## Module Dependency Verification

### backtest_process.py
- ✓ No circular imports
- ✓ Lazy imports for `ResultsService` and `mutation_service`
- ✓ Exports: `_save_run_record`, `_load_run_record`, `_list_freqtrade_runs`, `_process_matches_run_record`, `_resolve_process_exit_code`, `_terminate_process_tree`, `_mark_failed_run`, `_mark_stopped_run`, `_finalize_successful_backtest_run`, `_reconcile_stale_backtest_run`, `_watch_backtest_process`, `_start_backtest_watcher`, `stop_backtest_run`

### backtest_runner.py
- ✓ Depends on: `backtest_process`, `backtest_stream`, `mutation_service`, `config_svc`
- ✓ Exports: `load_live_strategy_code`, `load_live_strategy_parameters`, `_bootstrap_initial_version`, `_resolve_version_for_launch`, `_build_request_snapshot`, `_resolve_engine`, `get_options`, `run_backtest`

### backtest_stream.py
- ✓ Depends on: `backtest_process`, lazy import of `backtest_results`
- ✓ Exports: `_derive_backtest_progress`, `_terminal_backtest_progress`, `_sse`, `stream_log_response`, `stream_backtest_logs`

### backtest_results.py
- ✓ Depends on: `backtest_process`, `backtest_stream`, `results_svc`
- ✓ Exports: `_summarize_run_record`, `list_backtest_runs`, `get_backtest_run`, `compare_backtest_runs`, `get_summary`, `get_trades`

### backtest_diagnosis.py
- ✓ Depends on: `backtest_process`, `diagnosis_service`, `analyze_run_diagnosis_overlay`, `results_svc`, `mutation_service`
- ✓ Exports: `_derive_diagnosis_status`, `_default_ai_payload`, `_resolve_linked_version_for_run`, `get_backtest_run_diagnosis`

### proposal_service.py
- ✓ Depends on: `backtest_diagnosis`, `backtest_process`, `diagnosis_service`, `analyze_run_diagnosis_overlay`, `results_svc`
- ✓ Exports: `_build_proposal_candidate_response`, `create_backtest_run_proposal_candidate`

### runtime.py (Facade)
- ✓ Re-exports all public APIs
- ✓ Maintains backward compatibility
- ✓ Lazy imports to avoid cycles
- ✓ Keeps non-backtest functions: `download_data`, `stream_download_logs`, `list_configs`, `save_config`, `load_config`, `delete_config`, `validate_data`

## Functional Verification

### Backtest Workflow
1. ✓ `get_options()` returns strategies/timeframes/exchanges
2. ✓ `run_backtest()` launches backtest and returns run_id
3. ✓ `stream_backtest_logs()` streams live logs
4. ✓ `_reconcile_stale_backtest_run()` handles stale runs
5. ✓ `get_backtest_run()` retrieves run summary
6. ✓ `get_backtest_run_diagnosis()` returns diagnosis
7. ✓ `create_backtest_run_proposal_candidate()` creates candidate
8. ✓ `compare_backtest_runs()` compares two runs
9. ✓ `stop_backtest_run()` stops running backtest

### Download Workflow
1. ✓ `download_data()` launches download
2. ✓ `stream_download_logs()` streams download logs

### Config Workflow
1. ✓ `list_configs()` lists saved configs
2. ✓ `save_config()` saves config
3. ✓ `load_config()` loads config
4. ✓ `delete_config()` deletes config

### Validation Workflow
1. ✓ `validate_data()` validates pair/timeframe coverage

## Performance Verification

### Import Time
```python
import time
start = time.time()
from app.freqtrade.runtime import run_backtest
end = time.time()
print(f"Import time: {end - start:.3f}s")
```

Expected: < 0.5s (no significant change from original)

### Memory Usage
```python
import tracemalloc
tracemalloc.start()
from app.freqtrade.runtime import run_backtest
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {current / 1024 / 1024:.1f} MB")
```

Expected: No significant increase from original

## Regression Test Checklist

### Test: Facade Re-exports
```python
def test_runtime_facade_exports():
    from app.freqtrade import runtime
    
    # Verify all expected functions are exported
    assert hasattr(runtime, 'run_backtest')
    assert hasattr(runtime, 'stop_backtest_run')
    assert hasattr(runtime, 'stream_backtest_logs')
    assert hasattr(runtime, 'get_backtest_run_diagnosis')
    assert hasattr(runtime, 'create_backtest_run_proposal_candidate')
    assert hasattr(runtime, '_reconcile_stale_backtest_run')
    assert hasattr(runtime, '_watch_backtest_process')
    assert hasattr(runtime, '_is_terminal_status')
    assert hasattr(runtime, '_derive_backtest_progress')
    assert hasattr(runtime, 'load_live_strategy_code')
    assert hasattr(runtime, 'load_live_strategy_parameters')
    assert hasattr(runtime, '_load_run_record')
    assert hasattr(runtime, '_start_backtest_watcher')
    assert hasattr(runtime, '_summarize_run_record')
    assert hasattr(runtime, '_default_ai_payload')
    assert hasattr(runtime, '_resolve_linked_version_for_run')
    assert hasattr(runtime, '_derive_diagnosis_status')
    assert hasattr(runtime, 'download_data')
    assert hasattr(runtime, 'stream_download_logs')
    assert hasattr(runtime, 'list_configs')
    assert hasattr(runtime, 'save_config')
    assert hasattr(runtime, 'load_config')
    assert hasattr(runtime, 'delete_config')
    assert hasattr(runtime, 'validate_data')
    assert hasattr(runtime, 'results_svc')
    assert hasattr(runtime, 'config_svc')
    assert hasattr(runtime, 'persistence')
    assert hasattr(runtime, 'validation_svc')
    assert hasattr(runtime, 'analyze_run_diagnosis_overlay')
```

### Test: Progress Streaming
```python
def test_progress_streaming_unchanged():
    from app.freqtrade.backtest_stream import _derive_backtest_progress
    from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus
    
    # Create mock run record
    run = BacktestRunRecord(
        run_id="test",
        engine="freqtrade",
        strategy="TestStrat",
        version_id="v1",
        request_snapshot={},
        request_snapshot_schema_version=1,
        trigger_source="manual",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        completed_at=None,
        stop_requested_at=None,
        status=BacktestRunStatus.RUNNING,
        command="freqtrade backtest",
        artifact_path=None,
        raw_result_path=None,
        result_path=None,
        summary_path=None,
        exit_code=None,
        pid=None,
        error=None,
    )
    
    # Progress should be deterministic
    progress = _derive_backtest_progress(run)
    assert progress is not None
    assert "phase" in progress
    assert "percent" in progress
    assert "label" in progress
```

### Test: Proposal Candidate Response
```python
def test_proposal_candidate_response_unchanged():
    from app.freqtrade.proposal_service import _build_proposal_candidate_response
    from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus
    
    # Create mock run record
    run = BacktestRunRecord(
        run_id="test",
        engine="freqtrade",
        strategy="TestStrat",
        version_id="v1",
        request_snapshot={},
        request_snapshot_schema_version=1,
        trigger_source="manual",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        completed_at=None,
        stop_requested_at=None,
        status=BacktestRunStatus.COMPLETED,
        command="freqtrade backtest",
        artifact_path=None,
        raw_result_path=None,
        result_path=None,
        summary_path=None,
        exit_code=0,
        pid=None,
        error=None,
    )
    
    # Mock result object
    class MockResult:
        version_id = "v2"
        candidate_change_type = "PARAMETER_CHANGE"
        candidate_status = "staged"
        ai_mode = "parameter_suggestion"
        source_title = "Test Suggestion"
        message = "Test message"
        
        def to_response_payload(self):
            return {}
    
    response = _build_proposal_candidate_response(
        MockResult(),
        run_record=run,
        linked_version=None,
        linked_source="run",
        source_kind="ai_parameter_suggestion",
        source_index=0,
    )
    
    # Verify response structure
    assert response["baseline_run_id"] == "test"
    assert response["baseline_run_version_id"] == "v1"
    assert response["baseline_version_source"] == "run"
    assert response["source_kind"] == "ai_parameter_suggestion"
    assert response["source_index"] == 0
    assert response["version_id"] == "v2"
    assert response["change_type"] == "PARAMETER_CHANGE"
    assert response["status"] == "staged"
    assert response["ai_mode"] == "parameter_suggestion"
```

## Cleanup Verification

### Verify Old Code Removed
```bash
# The original runtime.py should be completely replaced
# Check that it's now a facade (should be ~350 lines, not 1000+)
wc -l app/freqtrade/runtime.py
```

Expected: ~350 lines (facade) instead of 1000+ lines (original)

## Sign-Off Checklist

- [ ] All 6 new modules created and syntactically correct
- [ ] `runtime.py` refactored to facade
- [ ] All imports work without modification
- [ ] All existing tests pass
- [ ] No circular dependencies
- [ ] Performance unchanged
- [ ] Memory usage unchanged
- [ ] Backward compatibility verified
- [ ] Documentation updated
- [ ] Ready for Phase 2 (download/config/validation refactoring)
