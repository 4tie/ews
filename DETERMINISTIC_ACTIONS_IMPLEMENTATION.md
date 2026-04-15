# Deterministic Proposal Actions

Deterministic proposal actions are the diagnosis-backed, non-AI-creative mutation path.

They exist so the app can stage useful parameter candidates from known diagnosis rules without writing live files or requiring free-form AI output.

## Current Canonical Actions

Implemented action families:

- `tighten_entries`
- `reduce_weak_pairs`
- `tighten_stoploss`
- `review_exit_timing`

Backward-compatibility alias:

- `accelerate_exits` -> `review_exit_timing`

## Where The Mapping Lives

### Diagnosis to action mapping
- `app/services/results/diagnosis_service.py`

Current rule-to-action mapping:
- `low_win_rate` -> `tighten_entries`
- `overtrading` -> `tighten_entries`
- `pair_dragger` -> `reduce_weak_pairs`
- `high_drawdown` -> `tighten_stoploss`
- `long_hold_time` -> `review_exit_timing`
- `exit_inefficiency` -> `review_exit_timing`

### Candidate creation
- `app/services/results/strategy_intelligence_apply_service.py`

This service:
- normalizes deterministic action aliases
- resolves the correct source item from diagnosis
- creates a new candidate version through `mutation_service.create_mutation()`
- keeps deterministic candidates parameter-only
- stamps them with `created_by="deterministic_proposal"`

### UI surfacing
- `web/static/js/pages/backtesting/results/proposal-workflow.js`

The Summary workflow shows deterministic actions as diagnosis-backed candidate options before looser suggestion paths.

## Contract

Deterministic actions must remain:

- version-first
- parameter-only
- non-destructive to live files
- linked to the originating baseline run and version
- explicitly accept/reject/rollback driven

They are not allowed to:

- bypass version staging
- auto-promote themselves
- rewrite live strategy code directly

## Current Behavior

When a completed run has diagnosis evidence:

1. diagnosis produces `proposal_actions`
2. the Backtesting Summary workflow renders those actions
3. the user clicks `Create Candidate`
4. the backend stages a new candidate version
5. the candidate can be rerun and compared like any other version
6. final promotion still requires an explicit decision

## Test Evidence

Deterministic actions are currently covered by:

- `test_deterministic_proposal_actions.py`
- `test_backtest_workflow_loop.py`
- `test_backtest_candidate_ui_contract.py`

These tests are the main proof that deterministic actions stay inside the versioned workflow contract.

## Remaining Improvements

Useful follow-up work, but not required for the current contract:

- richer preview of the exact parameter diff before staging
- batch creation of several deterministic candidates from one baseline run
- stronger browser-level proof of deterministic-action flows
