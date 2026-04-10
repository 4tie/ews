"""
Task classifier - classifies user requests into task types and determines pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from app.ai.models import get_dispatch, ModelResponse
from app.ai.prompts.trading import CLASSIFIER_SYSTEM_PROMPT


@dataclass
class Classification:
    task_types: list[str]
    complexity: Literal["low", "medium", "high"]
    requires_code: bool
    requires_structured_out: bool
    confidence: float
    recommended_pipeline: Literal["simple", "analysis", "debate", "code", "structured", "tool"]


async def classify_request(user_message: str) -> Classification:
    """Classify a user request to determine the appropriate AI pipeline."""
    messages = [
        {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    
    dispatch = get_dispatch()
    response = await dispatch.complete(
        messages=messages,
        model="openai/gpt-4o-mini",
        temperature=0.2,
        max_tokens=500,
    )
    
    try:
        result = json.loads(response.content)
        return Classification(
            task_types=result.get("task_types", ["casual_chat"]),
            complexity=result.get("complexity", "medium"),
            requires_code=result.get("requires_code", False),
            requires_structured_out=result.get("requires_structured_out", False),
            confidence=result.get("confidence", 0.5),
            recommended_pipeline=result.get("recommended_pipeline", "simple"),
        )
    except (json.JSONDecodeError, KeyError) as e:
        return Classification(
            task_types=["casual_chat"],
            complexity="medium",
            requires_code=False,
            requires_structured_out=False,
            confidence=0.3,
            recommended_pipeline="simple",
        )


async def classify_with_fallback(user_message: str) -> Classification:
    """Classify with fallback to default on failure."""
    try:
        return await classify_request(user_message)
    except Exception:
        return Classification(
            task_types=["casual_chat"],
            complexity="medium",
            requires_code=False,
            requires_structured_out=False,
            confidence=0.3,
            recommended_pipeline="simple",
        )


__all__ = ["Classification", "classify_request", "classify_with_fallback"]
