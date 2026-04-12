"""
AI Chat Services.
"""
from importlib import import_module

__all__ = [
    "LoopConfig",
    "LoopIteration",
    "LoopResult",
    "run_ai_loop",
    "analyze_with_two_mode",
    "PersistentAiChatService",
    "persistent_ai_chat_service",
]


def __getattr__(name: str):
    if name in {"LoopConfig", "LoopIteration", "LoopResult", "run_ai_loop", "analyze_with_two_mode"}:
        module = import_module("app.services.ai_chat.loop_service")
        return getattr(module, name)
    if name in {"PersistentAiChatService", "persistent_ai_chat_service"}:
        module = import_module("app.services.ai_chat.persistent_chat_service")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")