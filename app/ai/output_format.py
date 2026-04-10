"""
AI Output Format Enforcement - Two-Mode System.

Forces AI to return either:
- Mode A: Parameter-only recommendation (no code)
- Mode B: Code patch (unified diff format)

This module provides the system prompt and parsing logic to enforce this structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class OutputMode:
    mode: str
    is_applicable: bool
    parameters: dict[str, Any] | None
    code: str | None
    file: str | None
    class_name: str | None
    framework: str | None
    diff_lines: list[str]
    validation_errors: list[str]


TWO_MODE_SYSTEM_PROMPT = """You are a FreqTrade strategy expert. Return output in exactly ONE of these two modes:

MODE A - Parameter-only recommendation:
stoploss: <value>
trailing_stop: <true/false>
trailing_stop_positive: <value>
trailing_stop_positive_offset: <value>
minimal_roi: <JSON dict>
<param_name>: <value>
(NO code blocks, NO explanations, just key=value pairs)

MODE B - Code patch (unified diff format):
```python
# Full strategy code only
```
--- 
file: 
class: <StrategyClass>
framework: freqtrade

Rules:
1. Output ONLY Mode A OR Mode B - never both
2. For Mode A: List parameters as key: value pairs with no code
3. For Mode B: Must include file:, class:, and framework: headers
4. For Mode B: Use unified diff format starting with ```
5. NO explanations inside code blocks
6. NO vague "example" snippets
7. If you mix explanation with code, or provide vague examples, your response will be marked as "non-applicable suggestion"
"""


MODE_A_PARAM_PATTERNS = [
    r"stoploss\s*:\s*[-+]?[\d.]+",
    r"trailing_stop\s*:\s*(true|false)",
    r"trailing_stop_positive\s*:\s*[-+]?[\d.]+",
    r"trailing_stop_positive_offset\s*:\s*[-+]?[\d.]+",
    r"minimal_roi\s*:",
    r"[a-z_][a-z0-9_]*\s*:\s*[-+]?[\d.]+",
]


MODE_B_CODE_FENCE = "```python"
MODE_B_DIFF_MARKER = "---"
MODE_B_FILE_HEADER = re.compile(r"^file:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
MODE_B_CLASS_HEADER = re.compile(r"^class:\s*([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE | re.IGNORECASE)
MODE_B_FRAMEWORK_HEADER = re.compile(r"^framework:\s*(\S+)", re.MULTILINE | re.IGNORECASE)


def parse_ai_response(text: str) -> OutputMode:
    """
    Parse AI response and detect which mode was used.
    
    Returns OutputMode with mode classification and parsed data.
    """
    text = text or ""
    validation_errors: list[str] = []
    
    code_fence_count = text.count(MODE_B_CODE_FENCE)
    has_code_fence = code_fence_count >= 1
    
    mode_b_file_match = MODE_B_FILE_HEADER.search(text)
    mode_b_class_match = MODE_B_CLASS_HEADER.search(text)
    mode_b_framework_match = MODE_B_FRAMEWORK_HEADER.search(text)
    
    has_mode_b_headers = bool(mode_b_file_match and mode_b_class_match)
    
    mode_a_param_count = 0
    for pattern in MODE_A_PARAM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            mode_a_param_count += 1
    
    has_mode_a_params = mode_a_param_count >= 2
    
    if has_code_fence and has_mode_a_params:
        validation_errors.append(
            "Mixed output detected: both parameter recommendations and code blocks present. "
            "Response must be Mode A (parameters only) OR Mode B (code patch only)."
        )
        return OutputMode(
            mode="mixed",
            is_applicable=False,
            parameters=None,
            code=None,
            file=None,
            class_name=None,
            framework=None,
            diff_lines=[],
            validation_errors=validation_errors,
        )
    
    if has_code_fence:
        if not has_mode_b_headers:
            validation_errors.append(
                "Code block present but missing required headers (file:, class:). "
                "Mode B requires file: and class: headers before the code block."
            )
        
        code = _extract_code_block(text)
        
        file_name = mode_b_file_match.group(1) if mode_b_file_match else None
        class_name = mode_b_class_match.group(1) if mode_b_class_match else None
        framework = mode_b_framework_match.group(1) if mode_b_framework_match else None
        
        diff_lines = []
        if "diff" in text.lower() or "---" in text:
            diff_start = text.find("---")
            if diff_start >= 0:
                diff_lines = text[diff_start:].splitlines()[:80]
        
        if validation_errors:
            return OutputMode(
                mode="code_patch_invalid",
                is_applicable=False,
                parameters=None,
                code=code,
                file=file_name,
                class_name=class_name,
                framework=framework,
                diff_lines=diff_lines,
                validation_errors=validation_errors,
            )
        
        return OutputMode(
            mode="code_patch",
            is_applicable=True,
            parameters=None,
            code=code,
            file=file_name,
            class_name=class_name,
            framework=framework,
            diff_lines=diff_lines,
            validation_errors=[],
        )
    
    if has_mode_a_params:
        params = _extract_parameters(text)
        return OutputMode(
            mode="parameter_only",
            is_applicable=True,
            parameters=params,
            code=None,
            file=None,
            class_name=None,
            framework=None,
            diff_lines=[],
            validation_errors=[],
        )
    
    validation_errors.append(
        "Could not detect output mode. Response must be either Mode A (parameter recommendations) "
        "or Mode B (code patch with file:/class: headers)."
    )
    return OutputMode(
        mode="unknown",
        is_applicable=False,
        parameters=None,
        code=None,
        file=None,
        class_name=None,
        framework=None,
        diff_lines=[],
        validation_errors=validation_errors,
    )


def _extract_code_block(text: str) -> str | None:
    """Extract Python code from fenced code block."""
    fence_start = text.find(MODE_B_CODE_FENCE)
    if fence_start < 0:
        if "```" in text:
            fence_start = text.find("```")
        else:
            return None
    
    fence_end = text.find("```", fence_start + 9)
    if fence_end < 0:
        return None
    
    code = text[fence_start + 9:fence_end].strip()
    
    code = code.lstrip("python\n").lstrip("python")
    
    return code


def _extract_parameters(text: str) -> dict[str, Any]:
    """Extract parameter key:value pairs from text."""
    params: dict[str, Any] = {}
    
    param_pattern = re.compile(r"^([a-z_][a-z0-9_]*)\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
    
    for match in param_pattern.finditer(text):
        key = match.group(1).strip().lower()
        value_str = match.group(2).strip()
        
        if key in ("minimal_roi", "stoploss", "trailing_stop_positive", "trailing_stop_positive_offset"):
            if value_str.lower() in ("true", "false"):
                params[key] = value_str.lower() == "true"
            elif value_str.startswith("{"):
                try:
                    import json
                    params[key] = json.loads(value_str)
                except Exception:
                    params[key] = value_str
            else:
                try:
                    params[key] = float(value_str)
                except ValueError:
                    params[key] = value_str
        elif value_str.lower() in ("true", "false"):
            params[key] = value_str.lower() == "true"
        elif value_str.startswith("{"):
            try:
                import json
                params[key] = json.loads(value_str)
            except Exception:
                params[key] = value_str
        else:
            try:
                params[key] = float(value_str)
            except ValueError:
                params[key] = value_str
    
    return params


def validate_output_mode(text: str) -> tuple[bool, list[str]]:
    """
    Validate that AI output follows the two-mode format.
    
    Returns (is_valid, error_messages).
    """
    parsed = parse_ai_response(text)
    
    if parsed.is_applicable:
        return True, []
    
    return False, parsed.validation_errors


def format_parameter_recommendation(parameters: dict[str, Any]) -> str:
    """Format parameters as Mode A output."""
    lines = []
    for key, value in sorted(parameters.items()):
        if isinstance(value, dict):
            import json
            lines.append(f"{key}: {json.dumps(value)}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)