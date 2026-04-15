# Phase 1A Audit Report

## Scope: Extract smallest safe reusable desktop core slice

### Files Audited

#### 1. Models (app/models/)

| File | Status | Dependencies | Notes |
|------|--------|--------------|-------|
| `backtest_models.py` | ✅ MOVE AS-IS | pydantic only | Pure Pydantic models, no web deps |
| `optimizer_models.py` | ✅ MOVE AS-IS | pydantic only | Pure Pydantic models, no web deps |
| `settings_models.py` | ✅ MOVE AS-IS | pydantic, os, re | Pure Pydantic models, no web deps |

**Verdict**: All 3 model files are safe to move as-is. No FastAPI, HTTPException, or web-only types.

---

#### 2. Utils (app/utils/)

| File | Status | Dependencies | Notes |
|------|--------|--------------|-------|
| `paths.py` | ✅ MOVE AS-IS | os only | Pure path utilities, no web deps |
| `json_io.py` | ✅ MOVE AS-IS | json, os | Pure JSON I/O utilities, no web deps |
| `datetime_utils.py` | ✅ MOVE AS-IS | datetime | Pure datetime utilities, no web deps |

**Verdict**: All 3 utils files are safe to move as-is. No web dependencies.

---

#### 3. Services (app/services/)

| File | Status | Dependencies | Blocking Issues |
|------|--------|--------------|-----------------|
| `config_service.py` | ✅ MOVE AS-IS | freqtrade.settings, utils, paths | None - pure config logic |
| `validation_service.py` | ✅ MOVE AS-IS | freqtrade.executable, re, datetime | None - pure validation logic |
| `persistence_service.py` | ✅ MOVE AS-IS | utils, paths, os, json | None - pure persistence logic |

**Verdict**: All 3 service files are safe to move as-is. No web dependencies.

---

#### 4. Low-Level Freqtrade Modules (app/freqtrade/)

| File | Status | Dependencies | Blocking Issues |
|------|--------|--------------|-----------------|
| `commands.py` | ✅ MOVE AS-IS | freqtrade.executable | None - pure command builders |
| `executable.py` | ✅ MOVE AS-IS | os, shutil, sys | None - pure executable resolution |
| `paths.py` | ✅ MOVE AS-IS | os, utils.paths | None - pure path utilities |
| `settings.py` | ✅ MOVE AS-IS | freqtrade.paths, os | None - pure settings defaults |
| `cli_service.py` | ⚠️ MOVE WITH REFACTOR | mutation_service, config_service, utils, paths | **BLOCKER**: Imports `mutation_service` (higher-level service) |
| `engine.py` | ✅ MOVE AS-IS | engines.base, cli_service, config_service, validation_service, models, utils | None - pure engine logic |
| `result_parser.py` | ✅ MOVE AS-IS | engines.base, models, os, json, zipfile | None - pure result parsing |

**Verdict**: 
- 6 files move as-is (commands, executable, paths, settings, engine, result_parser)
- 1 file requires refactor (cli_service) - must extract mutation_service dependency

---

### Blocker Analysis: cli_service.py

**Issue**: `cli_service.py` imports `mutation_service` at line 10:
```python
from app.services.mutation_service import mutation_service
```

**Why it blocks Phase 1A**: 
- `mutation_service` is a higher-level workflow service (version lifecycle, promotion, rollback)
- It depends on results_service, diagnosis_service, and other workflow layers
- Phase 1A explicitly excludes higher-level services

**Minimal extraction-safe fix**:
- Extract the `_materialize_version_workspace()` method's dependency on `mutation_service`
- Replace with a parameter-based approach: pass `resolved_artifacts` dict instead of calling `mutation_service.resolve_effective_artifacts()`
- This keeps cli_service low-level and testable without workflow dependencies

**Implementation**:
1. Add new parameter to `_materialize_version_workspace()`: `resolved_artifacts: dict | None = None`
2. If `resolved_artifacts` is None, raise ValueError (caller must provide)
3. Remove the `mutation_service` import
4. Update `prepare_backtest_run()` to accept optional `resolved_artifacts` parameter
5. Document that callers must resolve artifacts externally (via mutation_service or other means)

---

### Summary

**Files to move as-is**: 9
- Models: 3
- Utils: 3
- Services: 3
- Freqtrade: 6 (commands, executable, paths, settings, engine, result_parser)

**Files to move with refactor**: 1
- Freqtrade: cli_service (remove mutation_service dependency)

**Total Phase 1A scope**: 10 files

**Blockers**: 1 (cli_service mutation_service dependency - RESOLVED with minimal refactor)

**Web-only dependencies found**: 0

---

## Target Structure After Phase 1A

```
app/core/
├── models/
│   ├── __init__.py
│   ├── backtest_models.py
│   ├── optimizer_models.py
│   └── settings_models.py
├── utils/
│   ├── __init__.py
│   ├── paths.py
│   ├── json_io.py
│   └── datetime_utils.py
├── services/
│   ├── __init__.py
│   ├── config_service.py
│   ├── validation_service.py
│   └── persistence_service.py
├── freqtrade/
│   ├── __init__.py
│   ├── commands.py
│   ├── executable.py
│   ├── paths.py
│   ├── settings.py
│   ├── cli_service.py (refactored)
│   ├── engine.py
│   └── result_parser.py
└── __init__.py
```

---

## Import Update Plan

After moving files to `app/core/`, these imports must be updated:

### In app/core/freqtrade/cli_service.py (refactored)
- Remove: `from app.services.mutation_service import mutation_service`
- Add parameter: `resolved_artifacts: dict | None = None` to `_materialize_version_workspace()`

### In app/freqtrade/ (remaining files that import from core)
- `backtest_process.py`: Update imports from `app.freqtrade.*` to `app.core.freqtrade.*`
- `backtest_runner.py`: Update imports from `app.freqtrade.*` to `app.core.freqtrade.*`
- `backtest_stream.py`: Update imports from `app.freqtrade.*` to `app.core.freqtrade.*`
- `backtest_results.py`: Update imports from `app.freqtrade.*` to `app.core.freqtrade.*`
- `backtest_diagnosis.py`: Update imports from `app.freqtrade.*` to `app.core.freqtrade.*`
- `proposal_service.py`: Update imports from `app.freqtrade.*` to `app.core.freqtrade.*`
- `runtime.py`: Update imports from `app.freqtrade.*` to `app.core.freqtrade.*`

### In app/services/ (remaining files that import from core)
- `results_service.py`: Update imports from `app.utils.*` to `app.core.utils.*`
- `results_service.py`: Update imports from `app.models.*` to `app.core.models.*`
- `mutation_service.py`: Update imports from `app.models.*` to `app.core.models.*`
- `ai_chat/persistent_chat_service.py`: Update imports from `app.utils.*` to `app.core.utils.*`
- `ai_chat/persistent_chat_service.py`: Update imports from `app.models.*` to `app.core.models.*`
- `autotune/auto_optimize_service.py`: Update imports from `app.models.*` to `app.core.models.*`

### In app/routers/ (all router files)
- Update imports from `app.models.*` to `app.core.models.*`
- Update imports from `app.utils.*` to `app.core.utils.*`
- Update imports from `app.services.config_service` to `app.core.services.config_service`
- Update imports from `app.services.validation_service` to `app.core.services.validation_service`
- Update imports from `app.services.persistence_service` to `app.core.services.persistence_service`

### In app/main.py
- Update imports from `app.models.*` to `app.core.models.*`
- Update imports from `app.utils.*` to `app.core.utils.*`

---

## Verification Checklist

- [ ] All 10 files copied to app/core/ with correct structure
- [ ] cli_service.py refactored to remove mutation_service dependency
- [ ] All imports updated in remaining app/ files
- [ ] app/core/__init__.py exports public APIs
- [ ] app/core/models/__init__.py exports all model classes
- [ ] app/core/utils/__init__.py exports all utility functions
- [ ] app/core/services/__init__.py exports all service classes
- [ ] app/core/freqtrade/__init__.py exports all freqtrade modules
- [ ] No circular imports between app/core and app/
- [ ] Current app still boots without errors
- [ ] Tests for moved files pass
- [ ] No web-only dependencies in app/core/

---

## Risks Before Phase 1B

1. **cli_service refactor**: Callers must now provide `resolved_artifacts` - need to verify all call sites updated
2. **Import cycles**: Verify no circular imports between app/core and remaining app/ services
3. **Persistence service**: Checkpoint/rollback expectations - verify no router-owned logic trapped in persistence layer
4. **Test coverage**: Ensure tests for moved files still pass with new import paths

