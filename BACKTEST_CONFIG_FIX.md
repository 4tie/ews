# Fix: Freqtrade "[stream] Connection closed" Error

## Problem

The backtest command was failing immediately with:
```
[stream] streaming started
$ <command>
[stream] Connection closed.
```

**Root Cause**: When a strategy version had **no parameters**, the system was still passing an empty config overlay file (`config.version.json`) containing `{}` to freqtrade. This caused freqtrade to fail during config parsing.

## Issue Details

In `app/services/freqtrade_cli_service.py`, the `_materialize_version_workspace` method would:

1. Resolve the version's parameters (which could be None or empty dict)
2. **Always** write a `config.version.json` file, even if empty
3. **Always** pass it to freqtrade via `--config config.version.json`

This meant that when a version had no parameters:
- `config.version.json` would contain `{}`
- Freqtrade would receive: `--config main.json --config config.version.json`
- Freqtrade's config parser would reject the empty config

## Solution

Modified `_materialize_version_workspace` to:

1. **Only write** `config.version.json` if the version actually has parameters
2. **Only include** the overlay config path in the command if it has parameters
3. If no parameters, pass only the main config file

### Code Changes

**File**: `app/services/freqtrade_cli_service.py` (lines 130-153)

```python
# Before: Always wrote overlay config
with open(workspace_paths["config_overlay_path"], "w", encoding="utf-8") as handle:
    json.dump(parameters_snapshot, handle, indent=2)

return {
    "config_paths": [base_config_path, workspace_paths["config_overlay_path"]],
    ...
}

# After: Only write overlay if we have parameters
config_overlay_path = None
config_paths = [base_config_path]
if parameters_snapshot:
    with open(workspace_paths["config_overlay_path"], "w", encoding="utf-8") as handle:
        json.dump(parameters_snapshot, handle, indent=2)
    config_overlay_path = workspace_paths["config_overlay_path"]
    config_paths.append(config_overlay_path)

return {
    "config_paths": config_paths,
    ...
}
```

## Behavior

### Version WITH parameters (normal case)
- ✅ Creates `config.version.json` with the parameters
- ✅ Passes both configs to freqtrade: `--config main.json --config config.version.json`
- ✅ Parameters override main config settings

### Version WITHOUT parameters (fixed case)
- ✅ Does NOT create `config.version.json`
- ✅ Passes only main config: `--config main.json`
- ✅ Uses main config settings as-is

## Testing

Created `test_backtest_config_fix.py` with two test cases:

1. **test_empty_parameters_doesnt_create_overlay_config()**
   - ✅ Verifies that versions with no parameters don't create overlay config
   - ✅ Verifies that only main config is passed to freqtrade

2. **test_with_parameters_creates_overlay_config()**
   - ✅ Verifies that versions with parameters still create overlay config
   - ✅ Verifies that both configs are passed correctly

### Test Results
```
[PASS] Empty parameters don't create overlay config file
[PASS] Parameters create overlay config file correctly
✅ All backtest config generation tests passed!
```

## Impact

- **Fixes**: Backtest runs now work correctly for versions without parameters
- **Backward Compatible**: Versions with parameters continue to work as before
- **No Changes Needed**: This is a silent fix in the infrastructure; no user data needs to be migrated

## Files Modified

- `app/services/freqtrade_cli_service.py` - Fixed `_materialize_version_workspace` method
- `test_backtest_config_fix.py` - New test file (verification)
