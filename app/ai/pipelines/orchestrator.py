"""
AI pipeline orchestrator - coordinates multi-step AI tasks.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.ai.models import get_dispatch
from app.ai.pipelines.classifier import Classification, classify_with_fallback
from app.ai.prompts.trading import (
    ANALYST_SYSTEM_PROMPT,
    CODE_GEN_SYSTEM_PROMPT,
    COMPOSER_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT_TEMPLATE,
    REASONER_SYSTEM_PROMPT,
    STRUCTURED_OUTPUT_SYSTEM_PROMPT,
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

    async def _complete_task(
        self,
        *,
        messages: list[dict[str, str]],
        task_type: str,
        complexity: str,
        temperature: float,
        max_tokens: int | None = None,
    ):
        return await self.dispatch.complete_routed(
            messages=messages,
            task_type=task_type,
            complexity=complexity,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def run_simple(self, context: PipelineContext) -> PipelineResult:
        messages = [
            {"role": "system", "content": REASONER_SYSTEM_PROMPT},
            {"role": "user", "content": context.user_message},
        ]
        routed = await self._complete_task(messages=messages, task_type="casual_chat", complexity="low", temperature=0.7)
        return PipelineResult(
            content=routed.response.content,
            classification=context.classification,
            metadata={"provider": routed.provider, "model": routed.model},
        )

    async def run_analysis(self, context: PipelineContext, analysis_context: str | None = None) -> PipelineResult:
        reasoner_messages = [
            {"role": "system", "content": REASONER_SYSTEM_PROMPT},
            {"role": "user", "content": context.user_message},
        ]
        if analysis_context:
            reasoner_messages.insert(1, {"role": "system", "content": analysis_context})

        reasoner = await self._complete_task(
            messages=reasoner_messages,
            task_type="analysis",
            complexity="medium",
            temperature=0.3,
            max_tokens=4000,
        )
        composer_messages = [
            {"role": "system", "content": COMPOSER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analysis: {reasoner.response.content}

Original request: {context.user_message}"},
        ]
        composer = await self._complete_task(
            messages=composer_messages,
            task_type="analysis",
            complexity="medium",
            temperature=0.5,
            max_tokens=4000,
        )
        return PipelineResult(
            content=composer.response.content,
            classification=context.classification,
            metadata={
                "reasoner_provider": reasoner.provider,
                "reasoner_model": reasoner.model,
                "composer_provider": composer.provider,
                "composer_model": composer.model,
            },
        )

    async def run_code_generation(self, context: PipelineContext, strategy_context: str | None = None) -> PipelineResult:
        system_prompt = CODE_GEN_SYSTEM_PROMPT
        if strategy_context:
            system_prompt = f"{system_prompt}

Strategy context:
{strategy_context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context.user_message},
        ]
        routed = await self._complete_task(
            messages=messages,
            task_type="code_generation",
            complexity="high",
            temperature=0.2,
            max_tokens=8000,
        )
        return PipelineResult(
            content=routed.response.content,
            classification=context.classification,
            metadata={"provider": routed.provider, "model": routed.model},
        )

    async def run_structured(self, context: PipelineContext) -> PipelineResult:
        messages = [
            {"role": "system", "content": STRUCTURED_OUTPUT_SYSTEM_PROMPT},
            {"role": "user", "content": context.user_message},
        ]
        routed = await self._complete_task(
            messages=messages,
            task_type="candidate_generation",
            complexity="medium",
            temperature=0.2,
        )
        return PipelineResult(
            content=routed.response.content,
            classification=context.classification,
            metadata={"provider": routed.provider, "model": routed.model},
        )

    async def run_debate(self, context: PipelineContext, goal_directive: str) -> PipelineResult:
        analyst_a_messages = [
            {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze with optimistic view: {context.user_message}"},
        ]
        analyst_b_messages = [
            {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
            {"role": "user", "content": f"Stress-test with downside view: {context.user_message}"},
        ]

        response_a, response_b = await asyncio.gather(
            self._complete_task(messages=analyst_a_messages, task_type="comparison", complexity="high", temperature=0.4, max_tokens=3000),
            self._complete_task(messages=analyst_b_messages, task_type="comparison", complexity="high", temperature=0.4, max_tokens=3000),
        )

        judge_messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT_TEMPLATE.format(goal_directive=goal_directive)},
            {"role": "user", "content": f"Analyst A: {response_a.response.content}

Analyst B: {response_b.response.content}"},
        ]
        judge = await self._complete_task(
            messages=judge_messages,
            task_type="comparison",
            complexity="high",
            temperature=0.3,
            max_tokens=3000,
        )
        return PipelineResult(
            content=judge.response.content,
            classification=context.classification,
            metadata={
                "analyst_a_provider": response_a.provider,
                "analyst_a_model": response_a.model,
                "analyst_b_provider": response_b.provider,
                "analyst_b_model": response_b.model,
                "judge_provider": judge.provider,
                "judge_model": judge.model,
            },
        )

    async def execute(self, context: PipelineContext) -> PipelineResult:
        if context.classification is None:
            context.classification = await classify_with_fallback(context.user_message)

        pipeline = context.classification.recommended_pipeline
        if pipeline == "simple":
            return await self.run_simple(context)
        if pipeline == "analysis":
            return await self.run_analysis(context)
        if pipeline == "code":
            return await self.run_code_generation(context)
        if pipeline == "structured":
            return await self.run_structured(context)
        if pipeline == "debate":
            return await self.run_debate(context, context.metadata.get("goal_directive", ""))
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
