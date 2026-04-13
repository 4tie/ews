# AGENTS.md

## Mission

This project is a controlled AI-assisted Freqtrade strategy improvement workbench.

## Local Startup

- Start the app with `python app\main.py`.
- Do not use raw `uvicorn --reload` as the documented workflow.
- `app/main.py` owns the repo-scoped reload policy and excludes workflow write paths under `data/backtest_runs/*/workspace`, `user_data/backtest_results/*`, and `data/versions/*/*.json`.

The product goal is NOT:
- autonomous AI code mutation
- random strategy rewrites
- opaque AI decisions
- hyperopt mixed with unrestricted code editing

The product goal IS:
- choose strategy and config
- run backtest
- analyze results
- propose improvements
- create a new candidate version
- rerun from that exact version
- compare baseline vs candidate
- explicitly accept or roll back

The required workflow is:
1. choose strategy and config
2. run backtest
3. load and explain results
4. propose either parameter changes or code changes
5. store every change as a new candidate version
6. rerun from that exact version
7. compare runs and versions
8. explicitly accept or roll back

## Non-Negotiable Rules

- Never overwrite strategy source code in place as the primary path.
- Every code or parameter mutation must produce a new versioned artifact first.
- Every run must be tied to the exact version_id used.
- Accept must promote an existing version.
- Rollback must promote a previous version.
- Hyperopt/optimizer is for parameter search only, not unrestricted strategy code mutation.
- AI may suggest and stage changes, but must not silently promote them.
- Do not create duplicate mutation, versioning, history, compare, or storage systems.
- Do not invent routes, pages, file names, or services without first checking whether they already exist.
- Do not create parallel APIs when an existing router/service can be extended safely.

## Correctness Lock Status ✅

All 12 core accept/promotion/rollback/rerun correctness requirements are LOCKED:

- **Accept** validates CANDIDATE status before write ✅
- **Promotion** is sole path to live files (`mutation_service._write_live_artifacts()`) ✅
- **Artifact gates** validate code snapshots before any write ✅
- **Rollback** restores exact artifacts from version lineage ✅
- **Rerun** uses version-exact isolated workspaces (never touches live) ✅
- **run_meta.json** is source of truth for version-run linkage ✅
- **No side-channel writes** to live files detected ✅

See [CORRECTNESS_LOCK.md](CORRECTNESS_LOCK.md) for full enforcement matrix.

**Test Coverage**: 9/9 tests passing (6 existing + 3 comprehensive lockdown tests)

**Key Authority Points**:
- `app/services/mutation_service.py: _write_live_artifacts()` — sole writer to user_data/
- `app/services/mutation_service.py: accept_version()` — CANDIDATE validator + pre-write gate
- `app/services/mutation_service.py: rollback_version()` — artifact validator + pre-write gate
- `app/freqtrade/cli_service.py: _materialize_version_workspace()` — non-invasive, run-scoped only

## Repo-First Behaviour

Before planning or coding:
1. inspect the actual repo structure
2. confirm exact file names and route names
3. confirm existing services and models
4. identify placeholders, TODOs, fake IDs, weak links, or dead flows
5. extend existing ownership points before proposing new files

When suggesting a new file, first prove no existing file already owns that responsibility.

When suggesting a new route, first prove no current route already covers the same responsibility under another name.

## Architecture Priorities

Always prioritize in this order:
1. architecture integrity
2. single mutation/version contract
3. run/version/result linkage
4. explicit accept/rollback lifecycle
5. optimizer boundary enforcement
6. AI routing and fallback policy
7. UI surfacing and test coverage

## Mutation Contract

All strategy edits must flow through one unified mutation/version service.

This includes:
- manual strategy edits
- AI apply-code
- AI apply-parameters
- evolution-generated candidates
- optimizer checkpoint promotion if applicable

Every mutation must capture:
- version_id
- parent_version_id
- strategy_name
- created_at
- created_by
- change_type
- summary
- diff or patch reference
- source artifact path
- status

No bypasses.

## Run Contract

Every backtest/evolution-triggered run must store:
- run_id
- strategy_name
- version_id
- parent_version_id if relevant
- trigger source
- timestamp
- result artifact path
- summary metrics

No run may exist without a traceable version link.

## AI Behaviour

AI is allowed to:
- explain results
- classify issues
- propose parameter changes
- propose code changes
- create candidate versions
- recommend which version seems stronger

AI is NOT allowed to:
- silently overwrite base strategy code
- silently accept/promote a version
- delete history
- destroy rollback paths
- mutate global settings without explicit instruction

## Optimizer Boundary

Optimizer/hyperopt may:
- search parameters
- produce parameter recommendations
- create parameter candidate versions

Optimizer/hyperopt may NOT:
- silently rewrite base strategy code
- act as the main code mutation engine
- bypass versioning
- bypass explicit accept/promote

## Planning Rules

When asked to audit or plan:
- ground every claim in actual repo files
- separate critical gaps from cleanup
- identify duplication and naming mistakes explicitly
- produce phased plans with exact files likely involved
- choose one highest-leverage first implementation task

When asked to implement:
- scope changes tightly
- preserve working behavior where possible
- avoid broad rewrites
- report exact files changed and why

## Quality Rules

- Prefer extending real existing services over introducing new abstractions.
- Prefer clarity and traceability over cleverness.
- Prefer small safe migrations over broad refactors.
- Prefer explicit state transitions over implicit side effects.
- Preserve backwards compatibility only when it does not keep architectural confusion alive.
