# Development Guidelines & Patterns

## Code Quality Standards

### Python Code Patterns

**Type Hints & Annotations**
- Comprehensive type hints on all function signatures (100% coverage observed)
- Union types for optional/nullable values: `str | None`, `dict | None`
- Generic types for collections: `list[dict]`, `dict[str, Any]`
- Return type annotations always present
- Example: `def analyze(run: dict, run_id: str = "", include_ai_narrative: bool = False) -> dict:`

**Error Handling**
- Explicit exception handling with specific exception types
- HTTPException for API errors with status codes and detail messages
- Try-except blocks with logging on failures
- Fallback mechanisms for optional features (e.g., AI narrative falls back to deterministic)
- Example: `except (OSError, json.JSONDecodeError) as exc: raise HTTPException(...) from exc`

**Documentation**
- Module-level docstrings explaining purpose and constraints
- Function docstrings with parameter descriptions
- Inline comments for complex logic sections
- Evidence-based comments citing specific numbers and data
- Example: `"""Deep Backtest Analysis Engine — evidence-based, strict output rules. Never invents data."""`

**Naming Conventions**
- Private functions prefixed with underscore: `_load_json_object`, `_derive_diagnosis_status`
- Constants in UPPER_SNAKE_CASE: `_TERMINAL_BACKTEST_STATUSES`, `_KNOWN_FAILURE_PREFIXES`
- Descriptive names reflecting purpose: `_reconcile_stale_backtest_run`, `_extract_process_failure_detail`
- Boolean functions prefixed with `is_` or `has_`: `_is_terminal_status`, `_process_matches_run_record`

**Code Organization**
- Logical grouping with section comments using dashes: `# ─────────────────────────────────────────`
- Related functions grouped together
- Helper functions placed before main functions that use them
- Constants defined at module top

### JavaScript Code Patterns

**Module Structure**
- ES6 modules with explicit imports/exports
- Single responsibility per file
- Utility functions exported for reuse
- Example: `export function parsePairInput(rawText, availablePairs) { ... }`

**Naming Conventions**
- camelCase for functions and variables: `renderSummaryCards`, `formatPct`, `applyTheme`
- UPPER_SNAKE_CASE for constants: `DEFAULT_ACCENT`, `ACCENT_KEY`, `VALID_PAIR_RE`
- Descriptive names reflecting action: `escapeHtml`, `normalizeSymbol`, `buildAvailableMaps`
- Private/internal functions prefixed with underscore: `_extract_level_message`, `_process_started_for_run`

**DOM Manipulation**
- Centralized element creation via utility: `el("div", { class: "..." })`
- Event listeners attached to specific elements
- Data attributes for configuration: `data-theme`, `data-density`, `data-color`
- HTML escaping for user-provided content: `escapeHtml(value)`

**Data Handling**
- Defensive null/undefined checks: `value == null ? EMPTY_VALUE : String(value)`
- Type coercion with validation: `toNumber(value)` returns null if invalid
- Normalization functions for input: `normalizeSymbol`, `safeNormalizeText`
- Mapping/lookup structures for performance: `combinedToCanonical`, `availableSet`

**Error Tolerance**
- Graceful degradation when data is missing
- Fallback values for missing fields
- Silent failures for non-critical operations
- Example: `if (typeof text.normalize === "function") { try { ... } catch (_) { } }`

## Semantic Patterns & Architectural Approaches

### Python Architectural Patterns

**Service Layer Pattern**
- Services encapsulate business logic (ResultsService, ConfigService, PersistenceService)
- Services expose public methods for specific operations
- Internal state managed within service instances
- Example: `results_svc.ingest_backtest_run(run_record)`, `config_svc.get_settings()`

**Factory & Resolution Pattern**
- Engine resolution based on configuration: `resolve_engine(settings)`
- Version resolution with fallback chain: `_resolve_version_for_launch(payload)`
- Lazy loading of optional features: `create_proposal_candidate_from_diagnosis` imported on demand

**Async/Await with Sync Bridges**
- Async functions for I/O operations: `async def run_backtest(payload: BacktestRunRequest)`
- Thread-based bridges for running async code from sync context: `_run_async_sync(coro_factory)`
- Process watchers in background threads: `_watch_backtest_process(run_id, process)`

**State Machine Pattern**
- Backtest run status transitions: QUEUED → RUNNING → COMPLETED/FAILED/STOPPED
- Status validation before state transitions
- Terminal status checks: `_is_terminal_status(status)`
- Reconciliation of stale states: `_reconcile_stale_backtest_run(run_record)`

**Evidence-Based Analysis**
- Deterministic diagnosis with specific thresholds
- Confidence levels based on data volume: "low" (<30 trades), "medium" (30-100), "high" (>100)
- Fallback to deterministic when AI unavailable
- Caching of expensive computations: `_narrative_cache_get/set`

### JavaScript Architectural Patterns

**Functional Composition**
- Pure functions for data transformation: `formatPct`, `toNumber`, `normalizeSymbol`
- Function chaining for complex operations: `buildSummarySnapshot` → `extractMetrics`
- Higher-order functions for reusable logic: `setActiveBtn(btns, attr, value)`

**Data Normalization Pipeline**
- Input validation and normalization: `safeNormalizeText`, `normalizeSymbol`
- Canonical form conversion: `canonicalFromSlash`, `canonicalFromCombined`
- Validation against allowlist: `availableSet.has(canonical)`
- Example: Raw input → normalized → canonical → validated

**Defensive Programming**
- Null coalescing for optional fields: `trade.profit_ratio ?? trade.profit_pct ?? 0`
- Safe property access: `row?.value && row.value !== EMPTY_VALUE`
- Type checking before operations: `Array.isArray(items)`, `isObject(value)`
- Graceful empty state handling: `<div class="info-empty">No data available.</div>`

**Persistence Pattern**
- Centralized storage via persistence module: `persistence.load(KEYS.THEME, "dark")`
- Key constants for storage: `KEYS.THEME`, `ACCENT_KEY`, `DENSITY_KEY`
- Load-apply-save cycle: Load → Apply to DOM → Save on change
- Example: `const savedTheme = persistence.load(KEYS.THEME, "dark"); applyTheme(savedTheme);`

**Event Delegation**
- Event listeners on button groups: `themeBtns.forEach(btn => btn.addEventListener("click", ...))`
- Data attributes for event routing: `btn.dataset.theme`, `btn.dataset.color`
- Active state management: `setActiveBtn(btns, attr, value)`

## Common Code Idioms & Practices

### Python Idioms

**Dictionary Unpacking & Merging**
```python
launch_payload = {**payload_data, "run_id": run_id}
response_payload = {**response_payload, "version_id": candidate_version_id}
```

**Conditional Assignment with Fallback**
```python
run_record.raw_result_path = (
    ingest_result.get("raw_result_path", run_record.raw_result_path)
)
```

**List Comprehension with Filtering**
```python
trades_with_profit = [t for t in trades if t.get("profit") is not None]
won = [t for t in trades_with_profit if t[\"profit\"] > 0]
```

**Safe Dictionary Access**
```python
value = summary.get("winRate")  # Returns None if missing
value = summary.get("winRate", 0)  # Returns 0 if missing
```

**Ternary Conditional**
```python
status = "ready" if summary_state.get("state") == "ready" else "pending"
```

**Context Manager Pattern**
```python
with open(path, "r", encoding="utf-8") as handle:
    return handle.read()
```

### JavaScript Idioms

**Optional Chaining & Nullish Coalescing**
```javascript
const value = trade.profit_ratio ?? trade.profit_pct ?? 0;
const color = btn?.dataset?.color;
```

**Array Methods for Transformation**
```javascript
const metrics = extractMetrics(summary, { expanded });
const filtered = metrics.filter((m) => m?.value && m.value !== EMPTY_VALUE);
const mapped = rows.map((row) => ({ label: row.key, value: row.profit }));
```

**Object Destructuring**
```javascript
const { strategyName, block } = unwrapStrategyEntry(summaryInput);
const { availableSet, combinedToCanonical, quoteSuffixes } = buildAvailableMaps(availablePairs);
```

**Template Literals for HTML**
```javascript
card.innerHTML = `
  <div class="card__label">${label}</div>
  <div class="card__value">${value}</div>
`;
```

**Set for Deduplication**
```javascript
const seen = new Set();
if (seen.has(canonical)) { hadDuplicates = true; continue; }
seen.add(canonical);
```

**Regular Expressions for Parsing**
```javascript
const scanRe = /([A-Za-z0-9]{2,24})\s*\/\s*([A-Za-z0-9]{2,24})|([A-Za-z0-9]{6,32})/g;
while ((match = scanRe.exec(text)) !== null) { ... }
```

## Frequently Used Annotations & Decorators

### Python

**Type Hints**
- `dict[str, Any]` - Dictionary with string keys and any values
- `list[dict]` - List of dictionaries
- `str | None` - String or None (union type)
- `Callable` - Callable/function type
- `HTTPException` - FastAPI exception for API errors

**Decorators (Implicit)**
- `@app.get()`, `@app.post()` - FastAPI route decorators (used in routers)
- `async def` - Async function marker for coroutines

### JavaScript

**JSDoc Comments** (observed in some files)
```javascript
/**
 * Parse a raw user-provided input string and extract unique valid trading pairs.
 * @param {string} rawText
 * @param {string[]=} availablePairs Optional allowlist of supported pairs.
 * @returns {{pairs: string[], invalidTokens: string[], hadDuplicates: boolean}}
 */
```

**Data Attributes** (HTML/DOM)
- `data-theme` - Theme identifier
- `data-density` - UI density setting
- `data-color` - Color value
- `data-font` - Font size setting

## Internal API Usage Patterns

### Python Service Calls

**Results Service**
```python
results_svc.ingest_backtest_run(run_record)
results_svc.load_run_summary_state(run)
results_svc.extract_run_summary_block(summary, strategy_name)
results_svc.compare_backtest_runs(left_run, right_run)
```

**Mutation Service**
```python
mutation_service.create_mutation(MutationRequest(...))
mutation_service.accept_version(version_id, notes="...")
mutation_service.get_version_by_id(version_id)
mutation_service.get_active_version(strategy_name)
mutation_service.link_backtest(version_id, run_id, profit_pct)
```

**Diagnosis Service**
```python
diagnosis_service.diagnose_run(
    run_record=run,
    summary_metrics=summary_metrics,
    summary_block=summary_block,
    trades=trades,
    results_per_pair=results_per_pair,
    request_snapshot=run.request_snapshot or {},
    request_snapshot_schema_version=run.request_snapshot_schema_version,
    linked_version=linked_version,
)
```

### JavaScript API Patterns

**Pair Parsing**
```javascript
const { pairs, invalidTokens, hadDuplicates } = parsePairInput(rawText, availablePairs);
```

**Result Rendering**
```javascript
renderSummaryCards(container, summary, { expanded: true });
renderTradesTable(wrapper, trades);
```

**Theme Management**
```javascript
persistence.load(KEYS.THEME, "dark");
persistence.save(KEYS.THEME, "light");
applyTheme(theme);
```

## Performance Considerations

### Python

**Lazy Loading**
- Optional features imported on demand: `from app.services.results.strategy_intelligence_apply_service import create_proposal_candidate_from_diagnosis`
- Conditional AI narrative generation only when requested

**Caching**
- Narrative cache with FIFO eviction at 100 entries
- Disk persistence of cache for recovery
- Cache key based on run_id

**Async I/O**
- Non-blocking file operations with aiofiles
- Process watchers in background threads
- Streaming responses for large logs

### JavaScript

**DOM Efficiency**
- Batch DOM updates: `container.innerHTML = ""; container.appendChild(grid);`
- Event delegation on button groups
- Minimal reflows with CSS class toggles

**Data Structure Selection**
- Set for O(1) deduplication: `seen.has(canonical)`
- Map for O(1) lookups: `combinedToCanonical.get(token)`
- Sorted arrays for binary search potential

**Regex Optimization**
- Compiled regex patterns: `const VALID_PAIR_RE = /^[A-Z0-9]+\/[A-Z0-9]+$/;`
- Global flag for multi-match: `/pattern/g`
- Longest-first suffix matching for correctness

## Testing Patterns

**Python**
- Test files follow pattern: `test_*.py`
- Comprehensive test coverage for critical paths
- Tests for service layer, API contracts, and workflows

**JavaScript**
- Example-based testing: `PAIR_PARSER_EXAMPLES` with expected outputs
- Test runner function: `runPairParserExamples()`
- Exposed to window for manual testing: `window._pairParser`

## Summary

This codebase emphasizes:
1. **Type Safety** - Comprehensive type hints and validation
2. **Evidence-Based Analysis** - Specific numbers, not vague conclusions
3. **Defensive Programming** - Null checks, fallbacks, graceful degradation
4. **Separation of Concerns** - Services, routers, utilities clearly separated
5. **Reusability** - Pure functions, composition, shared utilities
6. **Performance** - Async I/O, caching, efficient data structures
7. **Maintainability** - Clear naming, documentation, logical organization
