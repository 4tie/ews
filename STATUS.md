# 4tie Status

## Startup

- Start the app with `python app\main.py`
- Do not use raw `uvicorn --reload` as the documented startup path
- `app/main.py` owns the reload exclusions for:
  - `data/backtest_runs/*/workspace`
  - `user_data/backtest_results/*`
  - `data/versions/*/*.json`

## Current Product State

The current product is the Backtesting workflow, not the legacy optimizer page.

What is working now:
- Freqtrade-only backtest orchestration
- run-scoped version resolution and initial version bootstrap
- live log streaming for backtests and data downloads
- persisted run metadata under `data/backtest_runs/`
- normalized result ingestion and diagnosis
- deterministic proposal actions and AI-backed candidate staging
- candidate reruns from isolated workspaces
- baseline vs selected-candidate compare with version-aware evidence
- explicit accept, reject, rollback, and promote-as-new-strategy actions
- persistent AI chat threads and streamed job timelines
- Auto Optimize v1 on the Backtesting summary panel

## Product Truth

The app is already opinionated about the correct workflow:

1. choose strategy and config
2. run baseline backtest
3. inspect diagnosis and evidence
4. stage a new candidate version
5. rerun that exact candidate version
6. compare baseline vs candidate
7. explicitly decide the version outcome

That workflow is implemented across:
- `app/freqtrade/runtime.py`
- `app/services/results_service.py`
- `app/services/results/diagnosis_service.py`
- `app/services/results/strategy_intelligence_apply_service.py`
- `app/services/mutation_service.py`

## Locked Invariants

- candidate creation never writes live strategy files
- accept and rollback are the only live-write paths
- `run_meta.json` is the run/version linkage source of truth
- reruns use isolated workspaces under `data/backtest_runs/<run_id>/workspace/`
- compare is version-aware, not only metric-aware
- AI can stage candidates but cannot silently promote them

## What Is Still Incomplete

These are the real gaps left before the app can be called complete:

### 1. Legacy optimizer path is still partial
- `app/services/autotune/iterative_optimizer.py` is still a stub
- `web/static/js/pages/optimizer/optimizer.js` has no real stop or pause backend control
- `PersistenceService.rollback()` does not reactivate checkpoint state

### 2. There are still parallel-looking AI/optimizer surfaces
- `/backtesting` is the real workflow surface
- `/optimizer` still exists as a legacy page
- `/api/ai/evolution/*` still exists beside the run-scoped proposal flow and persistent AI chat flow

### 3. Browser proof should be expanded
- backend and contract coverage is strong
- browser-level regression proof for accept, reject, rollback, promote-as-new-strategy, and optimizer finalist selection should be broader

## Recommended Next Implementation Order

1. finish or retire the legacy `/optimizer` path
2. collapse parallel AI entrypoints into one clearly documented workflow
3. expand browser regression coverage around decision actions
4. only then spend time on visual polish and richer diff/audit rendering

## Short Summary

The versioned backtesting loop is already the product. The remaining work is convergence, not invention.

