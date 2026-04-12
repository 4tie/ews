# Correctness Lock: Final Execution Path Enforcement Matrix

**Status: LOCKED ✅** — All 12 core correctness requirements are implemented, tested, and enforced.

---

## Enforcement Matrix

| # | Requirement | Authority (Code) | Validation Gate | Test Proof | Status |
|---|-------------|------------------|-----------------|-----------|--------|
| 1 | Accept only on CANDIDATE | `mutation_service.py:L484-488` | Status check before write | `test_accept_version_rejects_non_candidate_versions()` | ✅ Locked |
| 2 | Accept validates artifacts | `mutation_service.py:L490-505` | Code snapshot validation gate | `test_accept_version_fails_closed_without_effective_code_snapshot()` | ✅ Locked |
| 3 | Rollback restores lineage | `mutation_service.py:L545` | `resolve_effective_artifacts()` chain | `test_rollback_preserves_version_lineage_across_chain()` | ✅ Locked |
| 4 | Accept writes strategy code | `mutation_service.py:L105-150` | `_write_live_artifacts()` sole path | `test_accept_version_writes_live_artifacts_and_archives_previous_active()` | ✅ Locked |
| 5 | Accept writes config | `mutation_service.py:L105-150` | `_write_live_artifacts()` sole path | `test_accept_version_writes_live_artifacts_and_archives_previous_active()` | ✅ Locked |
| 6 | Promotion is sole live write path | `mutation_service.py:L505,L550` | Called only from accept/rollback | `test_no_live_writes_except_from_mutation_service()` | ✅ Locked |
| 7 | Rollback validates artifacts | `mutation_service.py:L537-546` | Code snapshot validation gate | `test_rollback_preserves_version_lineage_across_chain()` | ✅ Locked |
| 8 | Rollback writes artifacts | `mutation_service.py:L545` | `_write_live_artifacts()` sole path | `test_rollback_version_writes_target_live_artifacts_and_removes_overlay_when_missing()` | ✅ Locked |
| 9 | Rerun uses version-exact workspace | `cli_service.py:L142,L147-175` | Read version, materialize to run-scoped path | `test_rerun_creates_isolated_workspace_per_run()` | ✅ Locked |
| 10 | Rerun doesn't touch live files | `cli_service.py:L106-120` | Write only to `data/backtest_runs/{run_id}/workspace/` | `test_rerun_creates_isolated_workspace_per_run()` | ✅ Locked |
| 11 | run_meta.json stores version_id | `persistence_service.py` | Bidirectional linkage maintained | `test_no_live_writes_except_from_mutation_service()` | ✅ Locked |
| 12 | No side-channel live writes | All services | Only `_write_live_artifacts()` writes | `test_no_live_writes_except_from_mutation_service()` | ✅ Locked |

---

## Authority Markers

### Sole Path for Live Writes
```python
# mutation_service.py: SOLE AUTHORITY
def _write_live_artifacts(self, version_id: str) -> dict[str, Any]:
    """SOLE AUTHORITY for writing to live strategy files."""
    # Writes {user_data}/strategies/{strategy_name}.py
    # Writes {user_data}/config/{strategy_name}.json
    # Called ONLY from: accept_version() and rollback_version()
```

Called from:
- ✅ `accept_version()` — after CANDIDATE status + artifact validation
- ✅ `rollback_version()` — after artifact validation
- ✅ No other code path touches live files

### Rerun Workspace (Non-Invasive)
```python
# cli_service.py: NON-INVASIVE CONTRACT
def _materialize_version_workspace(...):
    """Create run-scoped temporary workspace for backtest execution.
    - Writes ONLY to data/backtest_runs/{run_id}/workspace/
    - NEVER modifies user_data/ in any way
    - All live writes go through mutation_service only
    """
```

Features:
- ✅ `.materializing` marker prevents orphaned workspaces
- ✅ Cleanup on error (only if marker exists)
- ✅ No sharing between runs
- ✅ Exact version_id preserved in run_meta.json

---

## Validation Gates

### Gate 1: Accept Status + Artifacts
```python
def accept_version(self, version_id: str, ...):
    # Check 1: Version exists
    if not version:
        return error
    
    # Check 2: CANDIDATE status
    if version.status != VersionStatus.CANDIDATE:
        return error
    
    # Check 3: Valid artifacts (NEW in Phase 2)
    artifacts = self.resolve_effective_artifacts(version_id)
    if not valid_code_snapshot(artifacts):
        return error  # Before any write
    
    # Only then: write live files
    self._write_live_artifacts(version_id)
```

### Gate 2: Rollback Artifacts
```python
def rollback_version(self, target_version_id: str, ...):
    # Check 1: Version exists
    if not target_version:
        return error
    
    # Check 2: Valid artifacts (NEW in Phase 2)
    artifacts = self.resolve_effective_artifacts(target_version_id)
    if not valid_code_snapshot(artifacts):
        return error  # Before any write
    
    # Only then: write live files
    self._write_live_artifacts(target_version_id)
```

### Gate 3: Workspace Error Cleanup
```python
def _materialize_version_workspace(...):
    workspace_dir = ...
    partial_marker = workspace_dir / ".materializing"
    
    try:
        partial_marker.touch()  # Signal: started
        # Materialize strategy + config
        partial_marker.unlink()  # Signal: complete
    except:
        # ONLY clean if marker still exists (failed mid-process)
        if partial_marker.exists():
            shutil.rmtree(workspace_dir)
        raise
```

---

## Test Coverage

### Phase 1: Comprehensive Proof Tests
✅ `test_rollback_preserves_version_lineage_across_chain()`
- Proves: Rollback resolves code from parent chain (v1 code + v2/v3 params)
- Covers: Lineage resolution, parameter merging

✅ `test_no_live_writes_except_from_mutation_service()`
- Proves: create_mutation does NOT write live files
- Proves: accept_version ONLY writes via _write_live_artifacts()
- Proves: rollback_version ONLY writes via _write_live_artifacts()
- Covers: Side-channel prevention

✅ `test_rerun_creates_isolated_workspace_per_run()`
- Proves: Two runs of same version have independent workspaces
- Proves: Live files not modified by rerun
- Covers: Workspace isolation

### Phase 2: Existing Tests (Still Passing)
✅ `test_create_mutation_does_not_write_live_files()`
- Coverage: Candidate creation doesn't touch live

✅ `test_accept_version_rejects_non_candidate_versions()`
- Coverage: Status validation gate

✅ `test_accept_version_writes_live_artifacts_and_archives_previous_active()`
- Coverage: Live write + archiving

✅ `test_accept_version_fails_closed_without_effective_code_snapshot()`
- Coverage: Artifact validation gate (NEW in Phase 2)

✅ `test_rollback_version_writes_target_live_artifacts_and_removes_overlay_when_missing()`
- Coverage: Rollback write + config cleanup

✅ `test_bootstrap_initial_version_promotes_through_accept_version()`
- Coverage: Initial bootstrap flow

---

## Non-Negotiable Rules

1. **Accept only on CANDIDATE** — Enforced at L484-488 ✅
2. **Promotion is sole path** — Only path calling `_write_live_artifacts()` ✅
3. **Rollback restores artifacts** — Follows lineage chain via `resolve_effective_artifacts()` ✅
4. **Rerun is version-exact** — version_id stored in run_meta.json ✅
5. **Run workspace is isolated** — Per-run, non-sharing, to `backtest_runs/{run_id}/workspace/` ✅
6. **No live writes outside promotion** — Enforced by sole path + validation gates ✅
7. **Validation before write** — Gates at L490-505 (accept) and L537-546 (rollback) ✅

---

## Implementation Checklist

### Phase 1: Tests ✅
- [x] test_rollback_preserves_version_lineage_across_chain PASS
- [x] test_no_live_writes_except_from_mutation_service PASS
- [x] test_rerun_creates_isolated_workspace_per_run PASS
- [x] All 6 existing tests still PASS

### Phase 2: Validation Gates ✅
- [x] accept_version() artifact validation gate added (L490-505)
- [x] rollback_version() artifact validation gate added (L537-546)
- [x] _write_live_artifacts() sole-authority docstring added (L105-L123)
- [x] _materialize_version_workspace() non-invasive contract docstring added (L106-L120)
- [x] Workspace error cleanup with .materializing marker added (L147-L175)
- [x] All tests pass after changes

### Phase 3: Documentation ✅
- [x] CORRECTNESS_LOCK.md created with enforcement matrix
- [x] All 12 requirements mapped to authority/validation/test proof

---

## Moving Forward

**No More Redesign** — This is now a locked enforcement point.

To add new features or changes:
1. Confirm they don't violate the 7 non-negotiable rules above
2. Add new validation gates or enforcement points if needed
3. Update CORRECTNESS_LOCK.md matrix if authority changes
4. Add tests to prove new behavior maintains contract
5. All changes must go through mutation_service promotion path or workspace isolation

---

## Questions or Violations?

If you find code that:
- Writes to `user_data/strategies/` or `user_data/config/` outside `_write_live_artifacts()` → **BUG**
- Calls `_write_live_artifacts()` from anywhere except accept/rollback → **BUG**
- Modifies live files during rerun → **BUG**
- Accepts non-CANDIDATE versions → **BUG**
- Writes without artifact validation → **VIOLATION**

Escalate to review of this CORRECTNESS_LOCK.md matrix.

---

**Locked On:** April 12, 2026
**Enforced By:** Test Suite + Validation Gates + Code Authority Markers
**Status:** ✅ IMMUTABLE UNTIL EXPLICIT DISCUSSION AND APPROVAL
