# Backtesting Workflow Guide

The Backtesting page is the primary product workflow.

## Required Loop

Use `/backtesting` as a strict, version-aware decision loop:

1. choose strategy, timeframe, exchange, timerange, and pairs
2. optionally validate or download OHLCV data
3. run the baseline backtest
4. wait for persisted summary and diagnosis to become ready
5. create a candidate version from a grounded source
6. rerun that exact candidate version
7. compare `Baseline` vs `Selected Candidate`
8. explicitly accept, reject, roll back, or promote as a new strategy

## Current UI Surfaces

### Configuration
- strategy, timeframe, exchange, timerange, pairs
- load/save config buttons
- command preview updates from current form state

### Data Readiness
- validation calls `/api/backtest/validate-data`
- download calls `/api/backtest/download-data`
- both expose live status/log feedback

### Run Bar and Logs
- run backtest
- stop active run
- stream live logs from the backend

### Results Tabs
- `Summary` - diagnosis, proposal workflow, candidate state, auto optimize
- `Trades` - normalized trade table
- `Pairs` - per-pair result summary
- `Charts` - result charts
- `Compare` - baseline vs candidate evidence
- `History` - persisted run/version history
- `Configs` - saved config list
- `Export` - summary/trade export actions

## Candidate Sources Supported Now

Candidates can be staged from these sources:

- diagnosis-backed deterministic actions
- ranked issues
- parameter hints
- AI parameter suggestions
- AI chat drafts

Each source creates a new version record first. No source is allowed to silently update live strategy files.

## Deterministic Actions

Current diagnosis-driven action families are:

- `tighten_entries`
- `reduce_weak_pairs`
- `tighten_stoploss`
- `review_exit_timing`

`accelerate_exits` is retained only as a compatibility alias and normalizes to `review_exit_timing`.

## Compare Contract

The compare view is not only a metric table. It is version-aware evidence and currently includes:

- left and right run summaries
- metric deltas
- request snapshot diff
- version metadata
- parameter diff rows
- code diff summary
- pair-by-pair deltas
- diagnosis delta

In workflow mode, the intended comparison is `Baseline` vs `Selected Candidate`.

## Decision Rules

- **Accept as current strategy** - promote the selected candidate to the current live strategy
- **Promote as new strategy variant** - create a new live strategy lineage from the selected candidate
- **Reject** - keep the candidate out of the live lineage
- **Rollback** - restore a previous version as the live target

## Auto Optimize Role

`Auto Optimize v1` lives in the Summary panel and is anchored to the currently loaded baseline run.

It can:
- generate parameter-only candidate runs
- persist nodes, finalists, and near misses
- let the user select a finalist as the current workflow candidate

It does not bypass explicit accept/reject/rollback decisions.

## Completion Check

A candidate is decision-ready only when all of the following are true:

- the baseline run exists
- diagnosis status is `ready`
- a candidate version exists
- the candidate rerun completed successfully
- compare evidence is available for baseline vs candidate

If any of those are missing, the workflow is not complete yet.

