"""
Test script to verify two-mode output enforcement.
"""
from app.ai.output_format import parse_ai_response, validate_output_mode


def test_mode_a_parameter_only():
    text = """
stoploss: -0.10
trailing_stop: true
trailing_stop_positive: 0.05
minimal_roi: {"0": 0.05}
"""
    parsed = parse_ai_response(text)
    assert parsed.mode == "parameter_only", f"Expected parameter_only, got {parsed.mode}"
    assert parsed.is_applicable, f"Should be applicable: {parsed.validation_errors}"
    assert parsed.parameters is not None and parsed.parameters.get("stoploss") == -0.1
    print("[PASS] Mode A (parameter-only) test passed")


def test_mode_b_code_patch():
    text = """
```python
class MyStrategy(IStrategy):
    stoploss = -0.10
```
---
file: MyStrategy.py
class: MyStrategy
framework: freqtrade
"""
    parsed = parse_ai_response(text)
    assert parsed.mode == "code_patch", f"Expected code_patch, got {parsed.mode}"
    assert parsed.is_applicable, f"Should be applicable: {parsed.validation_errors}"
    print("[PASS] Mode B (code patch) test passed")


def test_mixed_output():
    text = """
stoploss: -0.10

```python
class MyStrategy(IStrategy):
    pass
```
"""
    parsed = parse_ai_response(text)
    assert parsed.mode == "mixed", f"Expected mixed, got {parsed.mode}"
    assert not parsed.is_applicable, "Mixed output should not be applicable"
    print("[PASS] Mixed output test passed")


def test_missing_headers():
    text = """
```python
class MyStrategy(IStrategy):
    pass
```
"""
    parsed = parse_ai_response(text)
    assert parsed.mode == "code_patch_invalid", f"Expected code_patch_invalid, got {parsed.mode}"
    assert not parsed.is_applicable, "Missing headers should not be applicable"
    print("[PASS] Missing headers test passed")


def test_unknown_output():
    text = "Hello, how are you?"
    parsed = parse_ai_response(text)
    assert parsed.mode == "unknown", f"Expected unknown, got {parsed.mode}"
    assert not parsed.is_applicable, "Unknown output should not be applicable"
    print("[PASS] Unknown output test passed")


if __name__ == "__main__":
    test_mode_a_parameter_only()
    test_mode_b_code_patch()
    test_mixed_output()
    test_missing_headers()
    test_unknown_output()
    print("\n[SUCCESS] All two-mode enforcement tests passed!")
