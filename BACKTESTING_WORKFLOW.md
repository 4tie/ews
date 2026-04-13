# Backtesting Workflow

## Workflow Guide

Use the Backtesting page as a fixed decision loop:

1. Configure Strategy in the left-side Configuration panel.
2. Run Backtest from the top run bar.
3. Review Diagnosis in Summary. Start with Primary Issues and use AI Overlay only as additional interpretation.
4. Open Proposal Workflow and create a versioned candidate from an actionable source.
5. Re-run the selected candidate, then open Compare to review baseline vs selected candidate evidence.
6. Decide the version from Candidate State.

## Main UI Surfaces

- Summary: shows the Workflow Guide, Run Diagnosis, Proposal Workflow, Candidate State, and inline Candidate Compare.
- Compare: shows baseline vs selected candidate after the candidate rerun is complete.
- History: shows persisted runs, version decisions, latest note snippet, and the audit timeline.
- AI Assistant: explains grounded run context, can regenerate replies, copy parameters/code, and create a versioned candidate from returned payloads.

## Decision Guidance

- Use **Accept as current strategy** when you want the selected candidate to become the live target for the current strategy.
- Use **Promote as new strategy variant** when you want to preserve the original strategy and create a separate live strategy lineage. This is the safer default when you do not want to overwrite the current live target.
- Use **Reject** when the candidate should stay out of the live strategy.
- Use **Rollback** when you need to restore the baseline version as the current live target.

## What Counts As Ready

A candidate is decision-ready only after:

- the baseline run is loaded
- diagnosis is ready
- a candidate version exists
- the selected candidate has been rerun successfully
- Compare shows baseline vs selected candidate evidence

After the decision, confirm the note snippet and audit timeline in History.
