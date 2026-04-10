"""
Model routing policy - determines which model to use based on task requirements.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class RoutingPolicy:
    task_type: str
    complexity: Literal["low", "medium", "high"]
    preferred_provider: str
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None


ROUTING_POLICIES: list[RoutingPolicy] = [
    RoutingPolicy(
        task_type="casual_chat",
        complexity="low",
        preferred_provider="openrouter",
        model="openai/gpt-4o-mini",
        temperature=0.7,
    ),
    RoutingPolicy(
        task_type="explanation",
        complexity="medium",
        preferred_provider="openrouter",
        model="openai/gpt-4o",
        temperature=0.5,
    ),
    RoutingPolicy(
        task_type="deep_reasoning",
        complexity="high",
        preferred_provider="openrouter",
        model="openai/gpt-4o",
        temperature=0.3,
        max_tokens=4000,
    ),
    RoutingPolicy(
        task_type="code_generation",
        complexity="high",
        preferred_provider="openrouter",
        model="openai/gpt-4o",
        temperature=0.2,
        max_tokens=8000,
    ),
    RoutingPolicy(
        task_type="structured_output",
        complexity="medium",
        preferred_provider="openrouter",
        model="openai/gpt-4o",
        temperature=0.2,
    ),
    RoutingPolicy(
        task_type="tool_calling",
        complexity="medium",
        preferred_provider="openrouter",
        model="openai/gpt-4o",
        temperature=0.3,
    ),
    RoutingPolicy(
        task_type="comparison",
        complexity="high",
        preferred_provider="openrouter",
        model="openai/gpt-4o",
        temperature=0.4,
        max_tokens=4000,
    ),
]


def get_routing_policy(
    task_type: str,
    complexity: str = "medium",
) -> RoutingPolicy:
    for policy in ROUTING_POLICIES:
        if policy.task_type == task_type and policy.complexity == complexity:
            return policy
    
    return ROUTING_POLICIES[0]


def get_fallback_policy() -> RoutingPolicy:
    return RoutingPolicy(
        task_type="fallback",
        complexity="medium",
        preferred_provider="openrouter",
        model="openai/gpt-4o-mini",
        temperature=0.7,
    )


__all__ = [
    "RoutingPolicy",
    "ROUTING_POLICIES",
    "get_routing_policy",
    "get_fallback_policy",
]
