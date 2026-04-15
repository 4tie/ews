# Phase 1A Verification Guide

## Quick Verification (5 minutes)

### 1. Check Core Layer Structure
```bash
# Verify all directories exist
test -d app/core && echo "✅ app/core exists"
test -d app/core/models && echo "✅ app/core/models exists"
test -d app/core/utils && echo "✅ app/core/utils exists"
test -d app/core/services && echo "✅ app/core/services exists"
test -d app/core/freqtrade && echo "✅ app/core/freqtrade exists"
```

### 2. Check All Files Exist
```bash
# Models
test -f app/core/models/__init__.py && echo "✅ models/__init__.py"
test -f app/core/models/backtest_models.py && echo "✅ models/backtest_models.py"
test -f app/core/models/optimizer_models.py && echo "✅ models/optimizer_models.py"
test -f app/core/models/settings_models.py && echo "✅ models/settings_models.py"

# Utils
test -f app/core/utils/__init__.py && echo "✅ utils/__init__.py"
test -f app/core/utils/paths.py && echo "✅ utils/paths.py"
test -f app/core/utils/json_io.py && echo "✅ utils/json_io.py"
test -f app/core/utils/datetime_utils.py && echo "✅ utils/datetime_utils.py"

# Services
test -f app/core/services/__init__.py && echo "✅ services/__init__.py"
test -f app/core/services/config_service.py && echo "✅ services/config_service.py"
test -f app/core/services/validation_service.py && echo "✅ services/validation_service.py"
test -f app/core/services/persistence_service.py && echo "✅ services/persistence_service.py"

# Freqtrade
test -f app/core/freqtrade/__init__.py && echo "✅ freqtrade/__init__.py"
test -f app/core/freqtrade/commands.py && echo "✅ freqtrade/commands.py"
test -f app/core/freqtrade/executable.py && echo "✅ freqtrade/executable.py"
test -f app/core/freqtrade/paths.py && echo "✅ freqtrade/paths.py"
test -f app/core/freqtrade/settings.py && echo "✅ freqtrade/settings.py"
test -f app/core/freqtrade/cli_service.py && echo "✅ freqtrade/cli_service.py"

# Core
test -f app/core/__init__.py && echo "✅ core/__init__.py"
```

### 3. Verify No Web Dependencies
```bash
# Should return NO results
echo "Checking for FastAPI imports..."
grep -r "from fastapi" app/core/ && echo "❌ FOUND FastAPI imports" || echo "✅ No FastAPI imports"

echo "Checking for HTTPException..."
grep -r "HTTPException" app/core/ && echo "❌ FOUND HTTPException" || echo "✅ No HTTPException"

echo "Checking for JSONResponse..."
grep -r "JSONResponse" app/core/ && echo "❌ FOUND JSONResponse" || echo "✅ No JSONResponse"

echo "Checking for StreamingResponse..."
grep -r "StreamingResponse" app/core/ && echo "❌ FOUND StreamingResponse" || echo "✅ No StreamingResponse"
```

### 4. Verify All Imports Use app.core.*
```bash
# Should return NO results (all imports should use app.core.*)
echo "Checking for non-core imports in app/core/..."
grep -r "from app\." app/core/ | grep -v "from app.core" && echo "❌ FOUND non-core imports" || echo "✅ All imports use app.core.*"
```

### 5. Test Core Imports
```bash
python3 << 'EOF'
try:
    from app.core.models import BacktestRunRequest, BacktestRunRecord
    print("✅ Models import OK")
except Exception as e:
    print(f"❌ Models import failed: {e}")

try:
    from app.core.utils import read_json, write_json, now_iso
    print("✅ Utils import OK")
except Exception as e:
    print(f"❌ Utils import failed: {e}")

try:
    from app.core.services import ConfigService, ValidationService, PersistenceService
    print("✅ Services import OK")
except Exception as e:
    print(f"❌ Services import failed: {e}")

try:
    from app.core.freqtrade import FreqtradeCliService, resolve_freqtrade_executable
    print("✅ Freqtrade import OK")
except Exception as e:
    print(f"❌ Freqtrade import failed: {e}")

print("\n✅ All Phase 1A imports working!")
EOF
```

---

## Detailed Verification (15 minutes)

### 1. Verify cli_service.py Refactoring
```bash
# Check that mutation_service import was removed
grep "from app.services.mutation_service" app/core/freqtrade/cli_service.py && echo "❌ mutation_service import still present" || echo "✅ mutation_service import removed"

# Check that resolved_artifacts parameter exists
grep "resolved_artifacts: dict\[str, Any\] | None = None" app/core/freqtrade/cli_service.py && echo "✅ resolved_artifacts parameter added" || echo "❌ resolved_artifacts parameter missing"

# Check that error message exists
grep "resolved_artifacts required for version_id" app/core/freqtrade/cli_service.py && echo "✅ Error message for missing resolved_artifacts" || echo "❌ Error message missing"
```

### 2. Verify All __init__.py Files Export Correctly
```bash
python3 << 'EOF'
import ast
import os

def check_init_file(path):
    with open(path, 'r') as f:
        content = f.read()
    
    # Check for __all__ definition
    if '__all__' in content:
        print(f"✅ {path} has __all__ defined")
        return True
    else:
        print(f"❌ {path} missing __all__")
        return False

init_files = [
    'app/core/__init__.py',
    'app/core/models/__init__.py',
    'app/core/utils/__init__.py',
    'app/core/services/__init__.py',
    'app/core/freqtrade/__init__.py',
]

all_ok = True
for init_file in init_files:
    if os.path.exists(init_file):
        if not check_init_file(init_file):
            all_ok = False
    else:
        print(f"❌ {init_file} not found")
        all_ok = False

if all_ok:
    print("\n✅ All __init__.py files properly configured")
else:
    print("\n❌ Some __init__.py files have issues")
EOF
```

### 3. Verify No Circular Imports
```bash
python3 << 'EOF'
import sys
import importlib

modules_to_test = [
    'app.core.models.backtest_models',
    'app.core.models.optimizer_models',
    'app.core.models.settings_models',
    'app.core.utils.paths',
    'app.core.utils.json_io',
    'app.core.utils.datetime_utils',
    'app.core.services.config_service',
    'app.core.services.validation_service',
    'app.core.services.persistence_service',
    'app.core.freqtrade.commands',
    'app.core.freqtrade.executable',
    'app.core.freqtrade.paths',
    'app.core.freqtrade.settings',
    'app.core.freqtrade.cli_service',
]

all_ok = True
for module_name in modules_to_test:
    try:
        importlib.import_module(module_name)
        print(f"✅ {module_name}")
    except Exception as e:
        print(f"❌ {module_name}: {e}")
        all_ok = False

if all_ok:
    print("\n✅ No circular imports detected")
else:
    print("\n❌ Some modules have import issues")
EOF
```

### 4. Verify Backward Compatibility
```bash
# Check that original files still exist
echo "Checking backward compatibility..."
test -f app/models/backtest_models.py && echo "✅ app/models/backtest_models.py still exists"
test -f app/utils/paths.py && echo "✅ app/utils/paths.py still exists"
test -f app/services/config_service.py && echo "✅ app/services/config_service.py still exists"

# Test that old imports still work
python3 << 'EOF'
try:
    from app.models import BacktestRunRequest
    print("✅ Old import path still works: from app.models import BacktestRunRequest")
except Exception as e:
    print(f"❌ Old import path broken: {e}")
EOF
```

### 5. Verify File Counts
```bash
echo "File count verification:"
echo "Models: $(ls -1 app/core/models/*.py | wc -l) files (expected 4)"
echo "Utils: $(ls -1 app/core/utils/*.py | wc -l) files (expected 4)"
echo "Services: $(ls -1 app/core/services/*.py | wc -l) files (expected 4)"
echo "Freqtrade: $(ls -1 app/core/freqtrade/*.py | wc -l) files (expected 6)"
```

---

## Comprehensive Verification (30 minutes)

### 1. Run All Tests
```bash
# Run tests for core layer (if tests exist)
pytest tests/ -v -k "core" 2>/dev/null || echo "No core-specific tests found"

# Run general tests
pytest tests/ -v 2>/dev/null || echo "No tests found or tests failed"
```

### 2. Check Code Quality
```bash
# Check for syntax errors
python3 -m py_compile app/core/models/*.py
python3 -m py_compile app/core/utils/*.py
python3 -m py_compile app/core/services/*.py
python3 -m py_compile app/core/freqtrade/*.py

echo "✅ All files compile without syntax errors"
```

### 3. Verify Documentation
```bash
# Check that all documentation files exist
test -f PHASE_1A_AUDIT.md && echo "✅ PHASE_1A_AUDIT.md exists"
test -f PHASE_1A_COMPLETION.md && echo "✅ PHASE_1A_COMPLETION.md exists"
test -f PHASE_1A_SUMMARY.md && echo "✅ PHASE_1A_SUMMARY.md exists"
test -f PHASE_1A_FILE_MANIFEST.md && echo "✅ PHASE_1A_FILE_MANIFEST.md exists"
test -f PHASE_1A_INDEX.md && echo "✅ PHASE_1A_INDEX.md exists"
```

---

## Verification Checklist

### Structure
- [ ] app/core/ directory exists
- [ ] app/core/models/ directory exists with 4 files
- [ ] app/core/utils/ directory exists with 4 files
- [ ] app/core/services/ directory exists with 4 files
- [ ] app/core/freqtrade/ directory exists with 6 files

### Dependencies
- [ ] No FastAPI imports in app/core/
- [ ] No HTTPException in app/core/
- [ ] No JSONResponse in app/core/
- [ ] No StreamingResponse in app/core/
- [ ] All imports use app.core.* paths

### Functionality
- [ ] All core modules import successfully
- [ ] No circular imports detected
- [ ] All __init__.py files have __all__ defined
- [ ] Old import paths still work (backward compatibility)

### Documentation
- [ ] PHASE_1A_AUDIT.md exists
- [ ] PHASE_1A_COMPLETION.md exists
- [ ] PHASE_1A_SUMMARY.md exists
- [ ] PHASE_1A_FILE_MANIFEST.md exists
- [ ] PHASE_1A_INDEX.md exists

### Refactoring
- [ ] cli_service.py mutation_service import removed
- [ ] cli_service.py has resolved_artifacts parameter
- [ ] cli_service.py has error handling for missing resolved_artifacts

---

## Verification Results Template

```
Phase 1A Verification Results
=============================

Date: [DATE]
Verifier: [NAME]

Quick Verification (5 min):
- [ ] Core layer structure: PASS / FAIL
- [ ] All files exist: PASS / FAIL
- [ ] No web dependencies: PASS / FAIL
- [ ] All imports use app.core.*: PASS / FAIL
- [ ] Core imports work: PASS / FAIL

Detailed Verification (15 min):
- [ ] cli_service.py refactoring: PASS / FAIL
- [ ] __init__.py files configured: PASS / FAIL
- [ ] No circular imports: PASS / FAIL
- [ ] Backward compatibility: PASS / FAIL
- [ ] File counts correct: PASS / FAIL

Comprehensive Verification (30 min):
- [ ] All tests pass: PASS / FAIL
- [ ] Code quality checks: PASS / FAIL
- [ ] Documentation complete: PASS / FAIL

Overall Result: ✅ PASS / ❌ FAIL

Notes:
[Any issues or observations]
```

---

## If Verification Fails

### Issue: Import errors
**Solution**: Check that all imports use `app.core.*` paths. Run `grep -r "from app\." app/core/ | grep -v "from app.core"` to find non-core imports.

### Issue: Circular imports
**Solution**: Check import order in __init__.py files. Ensure no module imports from a module that imports from it.

### Issue: Missing files
**Solution**: Verify all 19 files were created. Check file manifest in PHASE_1A_FILE_MANIFEST.md.

### Issue: cli_service.py errors
**Solution**: Verify mutation_service import was removed and resolved_artifacts parameter was added. Check PHASE_1A_COMPLETION.md for details.

### Issue: Old imports broken
**Solution**: Verify original files still exist in app/models/, app/utils/, app/services/. These should not be deleted.

---

## Success Criteria

✅ Phase 1A verification is successful if:
1. All 19 files exist in app/core/
2. No web dependencies found in app/core/
3. All imports use app.core.* paths
4. All core modules import successfully
5. No circular imports detected
6. Backward compatibility maintained
7. cli_service.py properly refactored
8. All documentation files exist

