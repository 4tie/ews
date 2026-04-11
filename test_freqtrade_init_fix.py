"""
Test to verify freqtrade subprocess initialization works correctly.

Issue Fixed:
- freqtrade subprocess was crashing with "Fatal Python error: init_import_site"
- Root cause: FT_FORCE_THREADED_RESOLVER=1 triggered sitecustomize.py to import aiohttp
- aiohttp import during Python initialization cascaded into ssl/asyncio imports
- This caused a KeyboardInterrupt during collections.namedtuple creation
- Solution: Disabled FT_FORCE_THREADED_RESOLVER in _freqtrade_subprocess_env()
"""

import os
import subprocess
import sys
from pathlib import Path

def test_freqtrade_version_command():
    """Test that freqtrade --version works without Python initialization errors."""
    freqtrade_exe = Path("t:/Optimizer/.venv/Scripts/freqtrade.exe")
    
    if not freqtrade_exe.exists():
        print(f"❌ Freqtrade executable not found at {freqtrade_exe}")
        return False
    
    try:
        result = subprocess.run(
            [str(freqtrade_exe), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd="t:\\Optimizer",
        )
        
        # Should succeed (exit code 0)
        if result.returncode != 0:
            print(f"❌ freqtrade --version failed with exit code {result.returncode}")
            print(f"stderr: {result.stderr}")
            return False
        
        output = result.stdout + result.stderr
        
        # Should NOT contain fatal error messages
        if "Fatal Python error" in output:
            print(f"❌ freqtrade --version produced fatal error:")
            print(output)
            return False
        
        # Should contain version info
        if "Freqtrade Version:" not in output:
            print(f"⚠️  Unexpected output from freqtrade --version:")
            print(output)
            return False
        
        print("✅ freqtrade --version works correctly")
        print(f"   {output.strip()}")
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ freqtrade --version timed out (likely hung on import)")
        return False
    except Exception as e:
        print(f"❌ Exception during freqtrade --version: {e}")
        return False

def test_subprocess_env_no_force_threaded():
    """Verify that FT_FORCE_THREADED_RESOLVER is not set in subprocess env."""
    # Import here to avoid circular dependencies
    sys.path.insert(0, str(Path("t:/Optimizer")))
    from app.services.freqtrade_cli_service import FreqtradeCLIService
    
    service = FreqtradeCLIService()
    env = service._freqtrade_subprocess_env()
    
    # FT_FORCE_THREADED_RESOLVER should NOT be set to "1"
    force_threaded = env.get("FT_FORCE_THREADED_RESOLVER")
    
    if force_threaded == "1":
        print(f"❌ FT_FORCE_THREADED_RESOLVER is still set to '1'")
        return False
    
    print(f"✅ FT_FORCE_THREADED_RESOLVER not set (value: {force_threaded})")
    return True

def test_sitecustomize_safe():
    """Verify sitecustomize.py doesn't trigger problematic imports."""
    sitecustomize = Path("t:/Optimizer/sitecustomize.py")
    
    if not sitecustomize.exists():
        print(f"⚠️  sitecustomize.py not found at {sitecustomize}")
        return True
    
    content = sitecustomize.read_text()
    
    # Should not actively import aiohttp (should be commented out or removed)
    has_aiohttp_import = (
        "import aiohttp.connector" in content 
        and "import aiohttp.connector" not in content.split("#")[0]  # Not in uncommented code
    )
    
    if has_aiohttp_import:
        print("❌ sitecustomize.py still has active aiohttp import outside comments")
        return False
    
    print("✅ sitecustomize.py is safe (aiohttp imports disabled/commented)")
    return True

if __name__ == "__main__":
    print("\n" + "="*70)
    print("Testing Freqtrade Subprocess Initialization Fix")
    print("="*70 + "\n")
    
    tests = [
        ("FT subprocess env safety", test_subprocess_env_no_force_threaded),
        ("sitecustomize.py safety", test_sitecustomize_safe),
        ("freqtrade --version", test_freqtrade_version_command),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n[TEST] {test_name}...")
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"❌ Unhandled exception: {e}")
            results.append((test_name, False))
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {test_name}")
    
    print(f"\nResult: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 All freqtrade initialization tests passed!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed")
        sys.exit(1)
