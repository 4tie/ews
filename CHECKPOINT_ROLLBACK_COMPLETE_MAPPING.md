# Checkpoint Rollback and EVOLUTION Version Creation - Complete Mapping

## EXECUTIVE SUMMARY

### 1. Checkpoint Rollback Entry Point
- **API Endpoint**: `POST /api/optimizer/runs/{run_id}/rollback/{checkpoint_id}`
- **Handler**: [app/routers/optimizer.py](app/routers/optimizer.py#L132)
- **Called From**: [web/static/js/pages/optimizer/checkpoint-panel.js](web/static/js/pages/optimizer/checkpoint-panel.js#L50) UI button click
- **Status**: ⚠️ **INCOMPLETE** - `persistence.rollback()` has TODO

### 2. EVOLUTION Version Creation Flow
- **When**: Triggered during checkpoint save
- **Where**: [app/services/autotune/iterative_optimizer.py](app/services/autotune/iterative_optimizer.py#L49) - `save_checkpoint()` method
- **How**: Two-step process:
  1. Save checkpoint JSON to disk
  2. Create EVOLUTION StrategyVersion via `mutation_service.create_mutation()`
- **Status**: ✅ **COMPLETE**

### 3. Parameter Storage
- **In Checkpoint**: Raw `params` dict in JSON
- **In EVOLUTION Version**: Wrapped in `parameters_snapshot` with nested keys
- **Files**: 
  - Checkpoint: `data/optimizer_runs/{run_id}/checkpoints/{checkpoint_id}.json`
  - Version: `data/versions/{strategy_name}/{version_id}.json`

### 4. RollbackRequest Model
- **Location**: [app/models/optimizer_models.py](app/models/optimizer_models.py#L91)
- **Usage**: Strategy version rollback (NOT checkpoint rollback)
- **Fields**: `target_version_id`, `reason`
- **API**: Different endpoint - `POST /api/versions/{strategy_name}/rollback`

### 5. UI/API for Checkpoint Rollback
- **UI**: Checkpoint list in [checkpoint-panel.js](web/static/js/pages/optimizer/checkpoint-panel.js)
- **Trigger**: Rollback button on each checkpoint
- **Flow**: User confirm → `api.optimizer.rollback(runId, checkId)` → Endpoint

### 6. Integration Tests
- **Status**: ⚠️ **MISSING** specific checkpoint rollback test
- **Should Test**: Checkpoint save→version creation→rollback flow

---

## DETAILED REFERENCE TABLE

| Component | File | Line | Details |
|-----------|------|------|---------|
| **UI - Checkpoint List** | `web/static/js/pages/optimizer/checkpoint-panel.js` | 12-20 | `loadCheckpoints(runId)` - fetches checkpoint list |
| **UI - Rollback Button** | `web/static/js/pages/optimizer/checkpoint-panel.js` | 50-57 | Click handler with confirmation dialog |
| **API Client** | `web/static/js/core/api.js` | 61 | `api.optimizer.rollback(runId, checkId)` |
| **Router - GET** | `app/routers/optimizer.py` | 129-131 | `@router.get("/runs/{run_id}/checkpoints")` |
| **Router - POST Rollback** | `app/routers/optimizer.py` | 132-137 | `@router.post("/runs/{run_id}/rollback/{checkpoint_id}")` |
| **Service - Rollback (INCOMPLETE)** | `app/services/persistence_service.py` | 94-97 | `rollback(run_id, checkpoint_id)` ⚠️ TODO |
| **Service - List Checkpoints** | `app/services/persistence_service.py` | 82-89 | `list_checkpoints(run_id)` |
| **Service - Load Checkpoint** | `app/services/persistence_service.py` | 90-92 | `load_checkpoint(run_id, checkpoint_id)` |
| **Service - Save Checkpoint** | `app/services/persistence_service.py` | 77-79 | `save_checkpoint(run_id, checkpoint_id, data)` |
| **Optimizer - Save Checkpoint** | `app/services/autotune/iterative_optimizer.py` | 49-75 | `save_checkpoint(epoch, params, profit_pct)` - creates EVOLUTION version |
| **Optimizer - List Checkpoints** | `app/services/autotune/iterative_optimizer.py` | 75-76 | `list_checkpoints()` |
| **Mutation - Create Mutation** | `app/services/mutation_service.py` | 632-690 | `create_mutation(request: MutationRequest)` |
| **Model - MutationRequest** | `app/models/optimizer_models.py` | 62-81 | Request structure for version creation |
| **Model - RollbackRequest** | `app/models/optimizer_models.py` | 91-94 | Request structure (for strategy version, NOT checkpoint) |
| **Model - StrategyVersion** | `app/models/optimizer_models.py` | 37-61 | Version storage model |
| **Model - ChangeType** | `app/models/optimizer_models.py` | 19 | Enum including `EVOLUTION` |
| **Model - VersionStatus** | `app/models/optimizer_models.py` | 7 | Enum including `CANDIDATE`, `ACTIVE` |

---

## METHOD SIGNATURES

### Checkpoint Rollback (Incomplete)
```python
# app/services/persistence_service.py:94
def rollback(self, run_id: str, checkpoint_id: str) -> dict:
    """Load and return checkpoint data as the new active state."""
    checkpoint = self.load_checkpoint(run_id, checkpoint_id)
    # TODO: apply rollback logic - re-activate this checkpoint's params
    return {"run_id": run_id, "checkpoint_id": checkpoint_id, "data": checkpoint}
```

### Load Checkpoint
```python
# app/services/persistence_service.py:90
def load_checkpoint(self, run_id: str, checkpoint_id: str) -> dict:
    path = resolve_safe(optimizer_runs_dir(), run_id, "checkpoints", f"{checkpoint_id}.json")
    return read_json(path, fallback={})
```

### Save Checkpoint
```python
# app/services/persistence_service.py:77
def save_checkpoint(self, run_id: str, checkpoint_id: str, data: dict) -> None:
    path = resolve_safe(optimizer_runs_dir(), run_id, "checkpoints", f"{checkpoint_id}.json")
    write_json(path, data)
```

### Checkpoint to EVOLUTION Version
```python
# app/services/autotune/iterative_optimizer.py:49
def save_checkpoint(self, epoch: int, params: dict, profit_pct: float, 
                   strategy_name: str = "unknown") -> dict:
    """Persist a good epoch result as a checkpoint with version control."""
    checkpoint_id = f"epoch_{epoch:04d}_{timestamp_slug()}"
    data = {
        "checkpoint_id": checkpoint_id,
        "epoch": epoch,
        "profit_pct": profit_pct,
        "params": params,
        "saved_at": now_iso(),
    }
    persistence.save_checkpoint(self.run_id, checkpoint_id, data)
    
    # Create EVOLUTION version
    mutation_result = mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.EVOLUTION,
            summary=f"Optimizer checkpoint epoch {epoch} with profit {profit_pct:.2f}%",
            created_by="optimizer",
            parameters={"hyperopt_params": params, "profit_pct": profit_pct},
            source_ref=checkpoint_id,
        )
    )
    data["version_id"] = mutation_result.version_id
    return data
```

### Create EVOLUTION Version
```python
# app/services/mutation_service.py:632
def create_mutation(self, request: MutationRequest) -> MutationResult:
    """Create a new version from a mutation request."""
    version_id = self._generate_version_id(request.strategy_name)
    parent_version_id = request.parent_version_id or self._get_active_version_id(request.strategy_name)
    
    version = StrategyVersion(
        version_id=version_id,
        parent_version_id=parent_version_id,
        strategy_name=request.strategy_name,
        created_at=datetime.now().isoformat(),
        created_by=request.created_by,
        change_type=request.change_type,  # ← EVOLUTION
        summary=request.summary,
        diff_ref=request.diff_ref,
        source_ref=request.source_ref,  # ← checkpoint_id
        source_kind=request.source_kind,
        source_context=dict(request.source_context or {}),
        status=VersionStatus.CANDIDATE,  # ← Always CANDIDATE
        code_snapshot=request.code,  # ← None for EVOLUTION
        parameters_snapshot=request.parameters,  # ← {hyperopt_params, profit_pct}
    )
    self._append_audit_event(version, "created", actor=request.created_by)
    self._save_version(version)
    
    return MutationResult(
        version_id=version_id,
        status="created",
        message=f"New candidate version {version_id} created from {request.change_type}",
    )
```

### Rollback Frontend
```javascript
// web/static/js/pages/optimizer/checkpoint-panel.js:50
listEl.addEventListener("click", async (e) => {
    const checkId = e.target.dataset.rollback;
    if (!checkId) return;
    if (!confirm(`Roll back to checkpoint ${checkId}?`)) return;
    try {
        await api.optimizer.rollback(runId, checkId);
        showToast("Rollback successful.", "success");
    } catch (e) {
        showToast("Rollback failed: " + e.message, "error");
    }
});
```

### API Client Call
```javascript
// web/static/js/core/api.js:67
optimizer: {
    rollback: (runId, checkId) => 
        api.post(`/api/optimizer/runs/${runId}/rollback/${checkId}`, {}),
}
```

### Backend Route Handler
```python
# app/routers/optimizer.py:132
@router.post("/runs/{run_id}/rollback/{checkpoint_id}")
async def rollback_to_checkpoint(run_id: str, checkpoint_id: str):
    """Roll back a legacy optimizer run to a specific checkpoint."""
    result = persistence.rollback(run_id, checkpoint_id)
    return {"run_id": run_id, "checkpoint_id": checkpoint_id, "status": "rolled_back", "data": result}
```

---

## DATA STRUCTURES

### Checkpoint JSON File
**Location**: `data/optimizer_runs/{run_id}/checkpoints/{checkpoint_id}.json`

```json
{
  "checkpoint_id": "epoch_0042_20260415_120000",
  "epoch": 42,
  "profit_pct": 5.23,
  "params": {
    "buy_rsi": 45,
    "sell_rsi": 75,
    "stoploss": -0.10,
    "trailing_stop": true
  },
  "saved_at": "2026-04-15T12:00:00",
  "version_id": "v_TestStrat_20260415_120000_xyz789"
}
```

### EVOLUTION StrategyVersion File
**Location**: `data/versions/{strategy_name}/{version_id}.json`

```json
{
  "version_id": "v_TestStrat_20260415_120000_xyz789",
  "parent_version_id": "v_TestStrat_20260414_110000_abc123",
  "strategy_name": "TestStrat",
  "created_at": "2026-04-15T12:00:00",
  "created_by": "optimizer",
  "change_type": "evolution",
  "summary": "Optimizer checkpoint epoch 42 with profit 5.23%",
  "diff_ref": null,
  "source_ref": "epoch_0042_20260415_120000",
  "source_kind": null,
  "source_context": {},
  "status": "candidate",
  "code_snapshot": null,
  "parameters_snapshot": {
    "hyperopt_params": {
      "buy_rsi": 45,
      "sell_rsi": 75,
      "stoploss": -0.10,
      "trailing_stop": true
    },
    "profit_pct": 5.23
  },
  "backtest_run_id": null,
  "backtest_profit_pct": null,
  "promoted_from_version_id": null,
  "promoted_at": null,
  "audit_events": [
    {
      "event_type": "created",
      "created_at": "2026-04-15T12:00:00",
      "actor": "optimizer",
      "note": null,
      "from_version_id": null
    }
  ]
}
```

### MutationRequest (Checkpoint → Version)
```python
MutationRequest(
    strategy_name="TestStrat",
    change_type=ChangeType.EVOLUTION,
    summary=f"Optimizer checkpoint epoch {epoch} with profit {profit_pct:.2f}%",
    created_by="optimizer",
    code=None,  # EVOLUTION: no code change
    parameters={
        "hyperopt_params": {...},
        "profit_pct": 5.23
    },
    parent_version_id=None,  # Auto-defaults to active
    source_ref="epoch_0042_20260415_120000",  # ← Links back to checkpoint
    source_kind=None,
    source_context={},
    diff_ref=None
)
```

### RollbackRequest Model
```python
class RollbackRequest(BaseModel):
    target_version_id: str  # Version ID to restore
    reason: Optional[str] = None  # Optional reason for rollback

# USAGE: Strategy version rollback, NOT checkpoint rollback
# API: POST /api/versions/{strategy_name}/rollback
```

---

## KEY FLOW DIAGRAMS

### Checkpoint Rollback API Call Chain
```
User clicks button
    ↓
checkpoint-panel.js:50
api.optimizer.rollback(runId, checkId)
    ↓ POST /api/optimizer/runs/opt-abc/rollback/epoch_0042_xyz
optimizer.py:132
rollback_to_checkpoint(run_id, checkpoint_id)
    ↓
persistence_service.py:94
rollback(run_id, checkpoint_id)  ← ⚠️ TODO: incomplete
    ↓
persistence_service.py:90
load_checkpoint(run_id, checkpoint_id)
    ↓ READ data/optimizer_runs/opt-abc/checkpoints/epoch_0042_xyz.json
Return checkpoint data
    ↓
UI Toast: "Rollback successful"
```

### Checkpoint → EVOLUTION Version Flow
```
iterative_optimizer.save_checkpoint(epoch, params, profit_pct, strategy_name)
    ↓
Step 1: persistence.save_checkpoint(run_id, checkpoint_id, data)
        WRITE: data/optimizer_runs/{run_id}/checkpoints/{checkpoint_id}.json
    ↓
Step 2: mutation_service.create_mutation(MutationRequest)
        strategy_name: TestStrat
        change_type: EVOLUTION
        parameters: {hyperopt_params, profit_pct}
        source_ref: checkpoint_id
    ↓
mutation_service._save_version(version)
        WRITE: data/versions/TestStrat/{version_id}.json
        status: CANDIDATE
    ↓
Return version_id to checkpoint
Update checkpoint with version_id
    ↓
Complete: Checkpoint + EVOLUTION version both created
```

---

## INCOMPLETE IMPLEMENTATION (TODO)

### Location
**File**: [app/services/persistence_service.py](app/services/persistence_service.py#L94)

```python
def rollback(self, run_id: str, checkpoint_id: str) -> dict:
    """Load and return checkpoint data as the new active state."""
    checkpoint = self.load_checkpoint(run_id, checkpoint_id)
    # TODO: apply rollback logic - re-activate this checkpoint's params
    return {"run_id": run_id, "checkpoint_id": checkpoint_id, "data": checkpoint}
```

### What's Missing
1. ✅ Load checkpoint from disk
2. ❌ Extract parameters from checkpoint
3. ❌ Apply parameters to optimizer run state
4. ❌ Record rollback event
5. ❌ Update optimizer run metadata

### What's NOT Supposed to Happen
- Does NOT automatically promote EVOLUTION version
- Does NOT write live strategy files (that's accept_version's job)
- Does NOT transition version status
- Checkpoint rollback is RUN-LOCAL only

---

## IMPORTANT DISTINCTIONS

### Checkpoint Rollback vs Strategy Version Rollback

| Aspect | Checkpoint Rollback | Strategy Version Rollback |
|--------|-------------------|--------------------------|
| **API Endpoint** | `POST /api/optimizer/runs/{run_id}/rollback/{checkpoint_id}` | `POST /api/versions/{strategy_name}/rollback` |
| **Router Handler** | `app/routers/optimizer.py:132` | `app/routers/versions.py:102` |
| **Request Model** | URL parameters | `RollbackRequest` model |
| **Service** | `persistence.rollback()` | `mutation_service.rollback_version()` |
| **Scope** | Run-local checkpoint | Strategy-wide version |
| **Status** | ⚠️ Incomplete | ✅ Complete |
| **Writes Live Files** | ❌ No | ✅ Yes |
| **Transitions Status** | ❌ No | ✅ Yes (to ACTIVE) |

### Checkpoint vs EVOLUTION Version

| Aspect | Checkpoint | EVOLUTION Version |
|--------|-----------|-------------------|
| **File Location** | `data/optimizer_runs/{run_id}/checkpoints/` | `data/versions/{strategy}/` |
| **Scope** | Run-local artifact | Strategy-wide versioning |
| **Contains** | params + epoch + profit | StrategyVersion object |
| **status** | N/A (not a version) | CANDIDATE (when created) |
| **code_snapshot** | N/A | null |
| **parameters_snapshot** | N/A | {hyperopt_params, profit_pct} |
| **Linkage** | One-way to version | Bidirectional (source_ref back) |
| **Created** | By `iterative_optimizer.save_checkpoint()` | Same call via `mutation_service.create_mutation()` |

---

## INTEGRATION TEST GAPS

### Missing Tests
1. ⚠️ No test: Checkpoint saved → EVOLUTION version created with correct fields
2. ⚠️ No test: Checkpoint JSON structure persistence
3. ⚠️ No test: EVOLUTION version accessible from checkpoint source_ref
4. ⚠️ No test: Multiple checkpoints create separate EVOLUTION versions
5. ⚠️ No test: Checkpoint rollback endpoint behavior

### Existing Tests
- ✅ `test_optimizer_auto_optimize_api.py` - Optimizer run creation
- ✅ `test_optimizer_auto_optimize_engine.py` - Optimizer engine operations

---

## STATUS ACKNOWLEDGMENT

From [STATUS.md](STATUS.md#L57):
```
## What Is Still Incomplete

### 1. Legacy optimizer path is still partial
- `app/services/autotune/iterative_optimizer.py` is still a stub
- `web/static/js/pages/optimizer/optimizer.js` has no real stop or pause backend control
- `PersistenceService.rollback()` does not reactivate checkpoint state
```

---

## KEY TAKEAWAYS

1. **Two Separate Rollback Systems**: Checkpoint rollback (incomplete, run-local) vs strategy version rollback (complete, strategy-wide)

2. **EVOLUTION Version Structure**: Created automatically when checkpoint saved, with `status=CANDIDATE` and `change_type=EVOLUTION`

3. **Parameter Storage**: Checkpoint stores flat `params` dict; EVOLUTION version wraps it in `parameters_snapshot` with `profit_pct`

4. **RollbackRequest**: Only used for strategy version rollback (different API), NOT checkpoint rollback

5. **Incomplete Implementation**: `persistence.rollback()` loads checkpoint but doesn't apply rollback logic (has TODO)

6. **Checkpoint → Version Linkage**: Via `source_ref` field pointing back to checkpoint_id

7. **No Integration Test**: The checkpoint rollback flow needs comprehensive testing

