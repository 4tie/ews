# 4tie / ews Status

## Startup

- Start local development with `python app\main.py`.
- Do not use raw `uvicorn --reload` as the documented workflow.
- `app/main.py` is the single owned startup entrypoint and carries the reload exclusions needed to avoid false restarts from workflow writes in:
  - `data/backtest_runs/*/workspace`
  - `user_data/backtest_results/*`
  - `data/versions/*/*.json`

## Current Product State

- The app is Freqtrade-only.
- Candidate creation is versioned and canonical-first.
- Candidate reruns are version-exact and run inside isolated workspaces.
- Compare is version-aware and decision-ready.
- The active workflow uses one selected-candidate state and compares `Baseline` vs `Selected Candidate`.
- The shared drawer is the only evolving AI chat workflow surface.

## Phase 4

Phase 4 is operational hardening after the reload fix, not feature rescue.

Current Phase 4 goals:
- keep `backtest.selectedCandidateVersionId` as the only selected-candidate state
- keep workflow compare on `Baseline` vs `Selected Candidate`
- preserve the canonical compare payload:
  - `versions`
  - `version_diff`
  - `parameter_diff_rows`
  - `code_diff`
  - `pairs`
  - `diagnosis_delta`
- run a smoke flow with:
  - candidate creation
  - rerun on the selected `version_id`
  - compare stability after workspace/result/version writes
- confirm the page does not restart itself from workflow file writes

## Locked Workflow Invariants

- Candidate creation never writes live files.
- Promotion and rollback are the only live-write paths.
- `run_meta.json` remains the source of truth for run/version linkage.
- Reruns must use version-exact isolated workspaces.
- Workflow compare must stay baseline-vs-selected-candidate in workflow mode.
- Generic left/right compare remains available only outside workflow mode.

## Remaining Work After Phase 4

Only polish-level work should remain after this phase:
- richer diff rendering
- optional raw patch viewer
- clearer history and audit visuals
- optional accept/reject notes
- frontend UX refinement
