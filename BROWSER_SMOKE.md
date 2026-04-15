# Browser Smoke

## Goal

Run a live browser smoke against the real Backtesting workflow and capture evidence under `output/playwright/`.

This smoke is for the implemented product path: `/backtesting`.

## Start The App

Use the repo-owned entrypoint:

```powershell
python app\main.py
```

## Open The App (Playwright CLI)

Preferred wrapper:

```powershell
bash "$env:USERPROFILE/.codex/skills/playwright/scripts/playwright_cli.sh" open http://127.0.0.1:5000/backtesting --headed
```

Equivalent direct CLI:

```powershell
npx --yes --package @playwright/cli playwright-cli open http://127.0.0.1:5000/backtesting --headed
```

## Core Workflow Smoke

1. Open `/backtesting`
2. Select a real strategy and timeframe
3. Set a reproducible timerange
4. Add or load pairs/config
5. Run `Validate Data`
6. If coverage is missing, run `Download Data` and wait for completion
7. Run the baseline backtest
8. Wait for Summary to show populated diagnosis and proposal sections
9. Save `output/playwright/summary-ready.png`
10. Create a candidate from a deterministic action or another grounded proposal source
11. Rerun the selected candidate version
12. Open `Compare` and confirm all of the following are visible:
    - metric deltas
    - request snapshot diff
    - version diff
    - parameter diff rows or code diff summary
    - pair comparison
    - diagnosis delta
13. Save `output/playwright/compare-ready.png`

## Decision Smoke

Run at least one of these paths end to end:

### Promote as new strategy variant
1. Open the accept dialog
2. Choose `Promote as new strategy variant`
3. Enter a new strategy name such as `<strategy>_v2`
4. Confirm success
5. Confirm the new strategy becomes selectable and active in its own lineage
6. Save `output/playwright/promote-new-strategy.png`

### Accept as current strategy
1. Accept the candidate as the current strategy
2. Confirm the active version changes for the existing strategy lineage
3. Save `output/playwright/accept-current-strategy.png`

### Reject
1. Reject the candidate
2. Confirm the candidate is marked rejected
3. Confirm the active live version does not change

### Rollback
1. Roll back to the chosen baseline or prior version
2. Confirm the live version pointer changes back
3. Confirm compare/history still show the audit trail

## Optional AI Smoke

1. Open the shared AI chat panel
2. Ask for diagnosis explanation using the loaded run context
3. If the assistant stages a candidate, confirm it remains a candidate only
4. Confirm no live promotion happens until an explicit user action

## Expected Evidence

The smoke is complete only when the browser proves:

- the baseline run completes and persists results
- diagnosis becomes ready
- candidate creation produces a versioned artifact first
- candidate rerun uses that exact version
- compare shows baseline vs selected-candidate evidence
- decision actions update version state without silent live writes

