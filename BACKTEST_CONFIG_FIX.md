# Version Workspace Config Overlay Fix

## Problem That Was Fixed

Candidate reruns were failing when a version had no parameter snapshot but still received an empty overlay config file.

That failure mode matters because the app allows:
- code-only candidates
- inherited-parameter candidates
- versions whose effective configuration comes entirely from the base config

## Current Correct Behavior

The workspace materialization path now lives in:

- `app/freqtrade/cli_service.py`

Inside `_materialize_version_workspace()`:

- write `config.version.json` only when the resolved version has a non-empty `parameters_snapshot`
- pass only the base config when there is no parameter overlay
- keep reruns version-exact without fabricating empty config overlays

## Why This Matters

This fix keeps the rerun contract correct:

- a candidate version can rerun even if it changed code only
- a candidate version can rely on inherited parameters from lineage
- the rerun workspace stays minimal and faithful to the effective version artifacts

## Resulting Rules

### If the version has parameters
- write a workspace overlay config
- pass base config plus overlay config to Freqtrade

### If the version has no parameters
- do not create an empty overlay file
- pass only the base config to Freqtrade

## Proof In Repo

The behavior is covered by:

- `test_backtest_config_fix.py`

That test file exists to prevent regressions where empty parameter overlays break reruns again.
