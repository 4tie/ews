# Remaining Implementation Map

This file replaces the old "everything is missing" view. Most of the app now exists. The remaining work is concentrated in a few incomplete surfaces.

## No Longer Missing

These areas are implemented and should not be described as TODO-only anymore:

- `app/models/*.py`
- `app/utils/paths.py`, `app/utils/datetime_utils.py`, `app/utils/json_io.py`
- backtest run orchestration in `app/freqtrade/runtime.py`
- isolated version workspace materialization in `app/freqtrade/cli_service.py`
- result ingestion and compare payloads in `app/services/results_service.py`
- diagnosis generation in `app/services/results/diagnosis_service.py`
- candidate staging in `app/services/results/strategy_intelligence_apply_service.py`
- version lifecycle in `app/services/mutation_service.py`
- persistent AI chat jobs and threads in `app/services/ai_chat/persistent_chat_service.py`
- backtesting page JS modules under `web/static/js/pages/backtesting/`
- version management routes in `app/routers/versions.py`
- settings, backtest, AI chat, and auto-optimize API routes

## What Is Still Actually Incomplete

### 1. Legacy optimizer implementation

This is the clearest remaining product gap.

#### Backend gaps
- `app/services/autotune/iterative_optimizer.py`
  - still does not launch real hyperopt work
  - stop is not wired to a subprocess
  - checkpoint creation exists, but the run loop does not

- `app/services/persistence_service.py`
  - `rollback()` still returns checkpoint data without reactivating anything

#### Frontend gaps
- `web/static/js/pages/optimizer/optimizer.js`
  - stop only stops the local log stream
  - pause is present in UI but not implemented

#### Product decision required
- either finish the `/optimizer` page end to end
- or retire/de-emphasize it and keep `Auto Optimize v1` on `/backtesting` as the only supported optimizer workflow

### 2. Workflow convergence

The repo currently has more than one surface that looks like "AI strategy improvement":

- `/api/backtest/runs/{run_id}/proposal-candidates`
- `/api/ai/chat/*`
- `/api/ai/evolution/*`
- `/backtesting` summary workflow
- `/optimizer` legacy page

The app will be easier to operate and document once one path is explicitly canonical and the others are framed as support layers or legacy adapters.

### 3. Browser-level proof for the full decision loop

The repo has strong contract coverage, but completion still benefits from stronger browser automation around:

- candidate creation from diagnosis
- candidate rerun and compare
- accept as current strategy
- promote as new strategy variant
- reject
- rollback
- auto-optimize finalist selection

### 4. Final UX polish

These are useful, but they are after the architectural cleanup above:

- richer compare diff rendering
- better audit/history visualization
- export/report formatting
- broader provider-specific settings UX

## Highest-Leverage Next Task

If only one implementation task should be chosen next, it should be:

**Finish or retire the legacy `/optimizer` path.**

Reason:
- it is the main remaining partially implemented product surface
- it creates confusion next to the implemented Backtesting + Auto Optimize workflow
- it still contains explicit backend and frontend TODOs

## Recommended Order

1. converge optimizer surfaces
2. converge AI entrypoints
3. add browser regression coverage for decision actions
4. polish compare, history, and reporting
