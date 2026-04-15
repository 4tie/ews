# Correctness Lock

This document describes the current execution contract that must remain true while the app evolves.

## Locked Workflow Guarantees

### Mutation and promotion
- candidate creation must create a versioned artifact first
- candidate creation must not write live `user_data` strategy files
- accept and rollback are the only live-write paths
- accept must validate `CANDIDATE` status before promotion
- rollback must restore the exact effective artifacts for the chosen version lineage
- promote-as-new-strategy must create a new lineage first, then promote that lineage explicitly

### Run linkage
- every backtest run must persist the exact `version_id` used
- `run_meta.json` is the run/version linkage source of truth
- completed runs link back to versions through `mutation_service.link_backtest()`

### Rerun isolation
- reruns must materialize a run-scoped workspace under `data/backtest_runs/<run_id>/workspace/`
- reruns must not mutate live strategy files in `user_data/`
- workspace materialization must clean up partial state on failure

### Compare evidence
- compare is version-aware, not only result-aware
- compare must continue to expose request snapshot diff, version diff, parameter diff rows, code diff summary, pair deltas, and diagnosis delta

### AI and optimizer boundaries
- AI may explain and stage candidates, but may not silently promote them
- Auto Optimize may generate candidate versions, but it may not bypass explicit version decisions
- hyperopt/optimizer is for parameter exploration, not unrestricted strategy code mutation

## Authority Points In Code

### Live-write authority
- `app/services/mutation_service.py`
  - `_write_live_artifacts()`
  - `accept_version()`
  - `rollback_version()`
  - `promote_as_new_strategy()`

No other path should write live strategy artifacts as part of the normal workflow contract.

### Version resolution and rerun isolation
- `app/freqtrade/runtime.py`
  - `_resolve_version_for_launch()`
  - `_bootstrap_initial_version()`
  - `run_backtest()`
  - `_finalize_successful_backtest_run()`

- `app/freqtrade/cli_service.py`
  - `_materialize_version_workspace()`

### Result normalization and compare
- `app/services/results_service.py`
  - `ingest_backtest_run()`
  - `summarize_backtest_run()`
  - `compare_backtest_runs()`

### Candidate staging
- `app/services/results/strategy_intelligence_apply_service.py`
  - `create_proposal_candidate_from_diagnosis()`
  - deterministic action handlers
  - AI-backed candidate staging helpers

## Test Evidence In Repo

These tests are the main proof points for the lock:

- `test_version_promotion_contract.py`
- `test_backtest_workflow_loop.py`
- `test_backtest_compare_contract.py`
- `test_backtest_config_fix.py`
- `test_backtest_run_control.py`
- `test_backtest_candidate_ui_contract.py`
- `test_ai_chat_candidate_contract.py`
- `test_optimizer_auto_optimize_api.py`
- `test_optimizer_auto_optimize_engine.py`

## What Counts As A Contract Violation

Treat these as bugs:

- any live write outside mutation-service promotion paths
- any rerun that edits live `user_data` artifacts
- any run persisted without a traceable version link
- any candidate auto-promoted without explicit user action
- any compare response that drops version-aware evidence
- any optimizer path that bypasses version staging

## Change Policy

If one of the authority points changes, do all of the following together:

1. update the implementation
2. update the tests that prove the contract
3. update this document

Do not change one of those in isolation.
