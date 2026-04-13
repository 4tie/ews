# Browser Smoke

## Goal

Run a full live browser smoke against the current Backtesting workflow without adding a Playwright test harness. Use Playwright CLI and store screenshots under `output/playwright/`.

## Start The App

Use the documented repo entrypoint:

```powershell
python app\main.py
```

## Open With Playwright CLI

Preferred wrapper:

```powershell
bash "$env:USERPROFILE/.codex/skills/playwright/scripts/playwright_cli.sh" open http://127.0.0.1:5000 --headed
```

Equivalent direct CLI:

```powershell
npx --yes --package @playwright/cli playwright-cli open http://127.0.0.1:5000 --headed
```

## Full Live Workflow Smoke

1. Open the Backtesting page.
2. Select the strategy, timeframe, timerange, and any required pairs/config.
3. Run the baseline backtest.
4. Wait for Summary to show Workflow Guide, Run Diagnosis, and Proposal Workflow.
5. Save a screenshot checkpoint to `output/playwright/summary-post-results.png`.
6. Create a candidate from an actionable proposal source.
7. Re-run the selected candidate.
8. Open Compare and confirm the decision snapshot and version diff are visible.
9. Save a screenshot checkpoint to `output/playwright/compare-decision-snapshot.png`.
10. Open the accept dialog and choose **Promote as new strategy variant**.
11. Enter a new strategy name such as `<current_strategy>_v2`.
12. Confirm that the strategy selector switches automatically to the new strategy after success.
13. Open History and confirm the latest note snippet, timeline rows, and active version pinning.
14. Save a screenshot checkpoint to `output/playwright/history-after-decision.png`.

## Secondary Branches

- Reject candidate: verify the candidate is marked rejected and the current live target stays unchanged.
- Accept as current strategy: verify the selected candidate becomes the live target for the current strategy.

## Expected Evidence

The smoke is complete only when you can verify all of the following in the browser:

- Workflow Guide reflects the current state
- Proposal Workflow explains the next action clearly
- Compare shows baseline vs selected candidate
- History shows audit evidence and note snippets
- Promote as new strategy variant keeps the original strategy intact
