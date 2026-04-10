"""
AI Chat Loop Service - Orchestrates AI conversation with two-mode output enforcement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.ai.models import get_dispatch, ModelResponse
from app.ai.output_format import (
    OutputMode,
    parse_ai_response,
    validate_output_mode,
    TWO_MODE_SYSTEM_PROMPT,
)
from app.ai.prompts.trading import TWO_MODE_SYSTEM_PROMPT as TRADING_TWO_MODE_SYSTEM_PROMPT
from app.ai.memory import get_thread_store, Thread
from app.ai.context_builder import build_strategy_context


@dataclass
class LoopConfig:
    max_iterations: int = 5
    temperature: float = 0.3
    model: str = "openai/gpt-4o"
    include_code: bool = True
    include_backtest: bool = True
    include_optimizer: bool = False


@dataclass
class LoopIteration:
    iteration: int
    ai_message: str
    parsed_mode: OutputMode
    validation_errors: list[str]


@dataclass
class LoopResult:
    success: bool
    iterations: list[LoopIteration]
    final_parameters: dict[str, Any] | None
    final_code: str | None
    error: str | None


async def run_ai_loop(
    user_message: str,
    strategy_name: str | None = None,
    strategy_code: str | None = None,
    backtest_results: dict[str, Any] | None = None,
    optimizer_results: dict[str, Any] | None = None,
    config: LoopConfig | None = None,
) -> LoopResult:
    """Run AI conversation loop with two-mode output enforcement."""
    config = config or LoopConfig()
    dispatch = get_dispatch()
    thread_store = get_thread_store()
    
    thread = thread_store.create_thread(metadata={"strategy": strategy_name})
    thread.add_message("user", user_message)
    
    context = build_strategy_context(
        strategy_name=strategy_name or "Unknown",
        code=strategy_code if config.include_code else None,
        backtest_results=backtest_results if config.include_backtest else None,
        optimizer_results=optimizer_results if config.include_optimizer else None,
    )
    
    system_prompt = f"{TRADING_TWO_MODE_SYSTEM_PROMPT}\n\nContext:\n{context}"
    
    iterations: list[LoopIteration] = []
    
    for i in range(config.max_iterations):
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(thread.get_messages())
        
        response = await dispatch.complete(
            messages=messages,
            model=config.model,
            temperature=config.temperature,
            max_tokens=4000,
        )
        
        thread.add_message("assistant", response.content)
        
        parsed = parse_ai_response(response.content)
        is_valid, errors = validate_output_mode(response.content)
        
        iteration = LoopIteration(
            iteration=i + 1,
            ai_message=response.content,
            parsed_mode=parsed,
            validation_errors=errors if not is_valid else [],
        )
        iterations.append(iteration)
        
        if parsed.is_applicable:
            if parsed.mode == "parameter_only" and parsed.parameters:
                return LoopResult(
                    success=True,
                    iterations=iterations,
                    final_parameters=parsed.parameters,
                    final_code=None,
                    error=None,
                )
            elif parsed.mode == "code_patch" and parsed.code:
                return LoopResult(
                    success=True,
                    iterations=iterations,
                    final_parameters=None,
                    final_code=parsed.code,
                    error=None,
                )
        
        if i < config.max_iterations - 1 and errors:
            feedback = f"Invalid output: {', '.join(errors)}. Please correct and provide valid output."
            thread.add_message("user", feedback)
    
    return LoopResult(
        success=False,
        iterations=iterations,
        final_parameters=None,
        final_code=None,
        error=f"Failed to produce valid output after {config.max_iterations} iterations",
    )


async def analyze_with_two_mode(
    user_message: str,
    context: str | None = None,
    strategy_code: str | None = None,
) -> OutputMode:
    """Analyze user request and return two-mode output."""
    dispatch = get_dispatch()
    
    full_context = context or ""
    if strategy_code:
        full_context = f"{full_context}\n\nStrategy Code:\n{strategy_code}"
    
    system_prompt = f"{TRADING_TWO_MODE_SYSTEM_PROMPT}"
    if full_context:
        system_prompt = f"{system_prompt}\n\nContext:\n{full_context}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    
    response = await dispatch.complete(
        messages=messages,
        model="openai/gpt-4o",
        temperature=0.3,
        max_tokens=4000,
    )
    
    return parse_ai_response(response.content)


__all__ = [
    "LoopConfig",
    "LoopIteration",
    "LoopResult",
    "run_ai_loop",
    "analyze_with_two_mode",
]
