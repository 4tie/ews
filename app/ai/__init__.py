r"""
AI modules for T:\Optimizer.
"""
from app.ai.output_format import (
    OutputMode,
    TWO_MODE_SYSTEM_PROMPT,
    parse_ai_response,
    validate_output_mode,
    format_parameter_recommendation,
)

from app.ai.prompts.trading import (
    TWO_MODE_SYSTEM_PROMPT as TRADING_TWO_MODE_SYSTEM_PROMPT,
    REASONER_SYSTEM_PROMPT,
    COMPOSER_SYSTEM_PROMPT,
    CODE_AWARE_ADVISOR_SYSTEM_PROMPT,
    ANALYST_SYSTEM_PROMPT,
    CODE_GEN_SYSTEM_PROMPT,
    CODE_EXPLAINER_SYSTEM_PROMPT,
    CLASSIFIER_SYSTEM_PROMPT,
    TOOL_CALLER_SYSTEM_PROMPT,
    STRUCTURED_OUTPUT_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT_TEMPLATE,
)

__all__ = [
    "OutputMode",
    "TWO_MODE_SYSTEM_PROMPT",
    "parse_ai_response",
    "validate_output_mode",
    "format_parameter_recommendation",
    "TRADING_TWO_MODE_SYSTEM_PROMPT",
    "REASONER_SYSTEM_PROMPT",
    "COMPOSER_SYSTEM_PROMPT",
    "CODE_AWARE_ADVISOR_SYSTEM_PROMPT",
    "ANALYST_SYSTEM_PROMPT",
    "CODE_GEN_SYSTEM_PROMPT",
    "CODE_EXPLAINER_SYSTEM_PROMPT",
    "CLASSIFIER_SYSTEM_PROMPT",
    "TOOL_CALLER_SYSTEM_PROMPT",
    "STRUCTURED_OUTPUT_SYSTEM_PROMPT",
    "JUDGE_SYSTEM_PROMPT_TEMPLATE",
]