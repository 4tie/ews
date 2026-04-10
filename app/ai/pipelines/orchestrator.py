"""
AI pipeline orchestrator - coordinates multi-step AI tasks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import json
import asyncio

from app.ai.models import get_dispatch, ModelResponse
from app.ai.pipelines.classifier import Classification, classify_with_fallback
from app.ai.prompts.trading import (
    REASONER_SYSTEM_PROMPT,
    COMPOSER_SYSTEM_PROMPT,
    CODE_AWARE_ADVISOR_SYSTEM_PROMPT,
    ANALYST_SYSTEM_PROMPT,
    CODE_GEN_SYSTEM_PROMPT,
    STRUCTURED_OUTPUT_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT_TEMPLATE,
)


@dataclass
class PipelineContext:
    user_message: str
    classification: Classification | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    content: str
    classification: Classification | None
    metadata: dict[str, Any]
    errors: list[str] = field(default_factory=list)


class PipelineOrchestrator:
    def __init__(self):
        self.dispatch = get_dispatch()
    
    async def run_simple(self, context: PipelineContext) -> PipelineResult:
        """Run a simple single-step conversation."""
        messages = [
            {"role": "system", "content": REASONER_SYSTEM_PROMPT},
            {"role": "user", "content": context.user_message},
        ]
        
        response = await self.dispatch.complete(
            messages=messages,
            model="openai/gpt-4o",
            temperature=0.7,
        )
        
        return PipelineResult(
            content=response.content,
            classification=context.classification,
            metadata={"model": response.model},
        )
    
    async def run_analysis(
        self,
        context: PipelineContext,
        analysis_context: str | None = None,
    ) -> PipelineResult:
        """Run analysis pipeline: reason then compose."""
        reasoner_messages = [
            {"role": "system", "content": REASONER_SYSTEM_PROMPT},
            {"role": "user", "content": context.user_message},
        ]
        
        if analysis_context:
            reasoner_messages.insert(1, {"role": "system", "content": analysis_context})
        
        reasoner_response = await self.dispatch.complete(
            messages=reasoner_messages,
            model="openai/gpt-4o",
            temperature=0.3,
            max_tokens=4000,
        )
        
        composer_messages = [
            {"role": "system", "content": COMPOSER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analysis: {reasoner_response.content}\n\nOriginal request: {context.user_message}"},
        ]
        
        composer_response = await self.dispatch.complete(
            messages=composer_messages,
            model="openai/gpt-4o",
            temperature=0.5,
            max_tokens=4000,
        )
        
        return PipelineResult(
            content=composer_response.content,
            classification=context.classification,
            metadata={"reasoner_model": reasoner_response.model, "composer_model": composer_response.model},
        )
    
    async def run_code_generation(
        self,
        context: PipelineContext,
        strategy_context: str | None = None,
    ) -> PipelineResult:
        """Run code generation pipeline."""
        system_prompt = CODE_GEN_SYSTEM_PROMPT
        
        if strategy_context:
            system_prompt = f"{system_prompt}\n\nStrategy context:\n{strategy_context}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context.user_message},
        ]
        
        response = await self.dispatch.complete(
            messages=messages,
            model="openai/gpt-4o",
            temperature=0.2,
            max_tokens=8000,
        )
        
        return PipelineResult(
            content=response.content,
            classification=context.classification,
            metadata={"model": response.model},
        )
    
    async def run_structured(
        self,
        context: PipelineContext,
    ) -> PipelineResult:
        """Run structured output pipeline."""
        messages = [
            {"role": "system", "content": STRUCTURED_OUTPUT_SYSTEM_PROMPT},
            {"role": "user", "content": context.user_message},
        ]
        
        response = await self.dispatch.complete(
            messages=messages,
            model="openai/gpt-4o",
            temperature=0.2,
        )
        
        return PipelineResult(
            content=response.content,
            classification=context.classification,
            metadata={"model": response.model},
        )
    
    async def run_debate(
        self,
        context: PipelineContext,
        goal_directive: str,
    ) -> PipelineResult:
        """Run debate pipeline: two analyses then judge."""
        analyst_a_messages = [
            {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze with optimistic view: {context.user_message}"},
        ]
        
        analyst_b_messages = [
            {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
            {"role": "user", "content": f"Stress-test with downside view: {context.user_message}"},
        ]
        
        response_a, response_b = await asyncio.gather(
            self.dispatch.complete(
                messages=analyst_a_messages,
                model="openai/gpt-4o",
                temperature=0.4,
                max_tokens=3000,
            ),
            self.dispatch.complete(
                messages=analyst_b_messages,
                model="openai/gpt-4o",
                temperature=0.4,
                max_tokens=3000,
            ),
        )
        
        judge_messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT_TEMPLATE.format(goal_directive=goal_directive)},
            {"role": "user", "content": f"Analyst A: {response_a.content}\n\nAnalyst B: {response_b.content}"},
        ]
        
        judge_response = await self.dispatch.complete(
            messages=judge_messages,
            model="openai/gpt-4o",
            temperature=0.3,
            max_tokens=3000,
        )
        
        return PipelineResult(
            content=judge_response.content,
            classification=context.classification,
            metadata={
                "analyst_a": response_a.model,
                "analyst_b": response_b.model,
                "judge": judge_response.model,
            },
        )
    
    async def execute(self, context: PipelineContext) -> PipelineResult:
        """Execute the appropriate pipeline based on classification."""
        if context.classification is None:
            context.classification = await classify_with_fallback(context.user_message)
        
        pipeline = context.classification.recommended_pipeline
        
        if pipeline == "simple":
            return await self.run_simple(context)
        elif pipeline == "analysis":
            return await self.run_analysis(context)
        elif pipeline == "code":
            return await self.run_code_generation(context)
        elif pipeline == "structured":
            return await self.run_structured(context)
        elif pipeline == "debate":
            return await self.run_debate(context, context.metadata.get("goal_directive", ""))
        else:
            return await self.run_simple(context)


_default_orchestrator: PipelineOrchestrator | None = None


def get_orchestrator() -> PipelineOrchestrator:
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = PipelineOrchestrator()
    return _default_orchestrator


__all__ = [
    "PipelineContext",
    "PipelineResult",
    "PipelineOrchestrator",
    "get_orchestrator",
]
