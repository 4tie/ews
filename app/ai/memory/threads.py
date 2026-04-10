"""
AI Conversation Memory - Thread management.
"""
from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Thread:
    id: str
    messages: list[Message] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def add_message(self, role: str, content: str) -> Message:
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.updated_at = time.time()
        return msg
    
    def get_messages(self) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.messages]


class InMemoryThreadStore:
    def __init__(self):
        self._threads: dict[str, Thread] = {}
    
    def create_thread(self, metadata: dict[str, Any] | None = None) -> Thread:
        thread_id = str(uuid.uuid4())
        thread = Thread(id=thread_id, metadata=metadata or {})
        self._threads[thread_id] = thread
        return thread
    
    def get_thread(self, thread_id: str) -> Thread | None:
        return self._threads.get(thread_id)
    
    def add_message(self, thread_id: str, role: str, content: str) -> Message | None:
        thread = self.get_thread(thread_id)
        if thread:
            return thread.add_message(role, content)
        return None
    
    def get_messages(self, thread_id: str) -> list[dict[str, str]]:
        thread = self.get_thread(thread_id)
        if thread:
            return thread.get_messages()
        return []
    
    def delete_thread(self, thread_id: str) -> bool:
        if thread_id in self._threads:
            del self._threads[thread_id]
            return True
        return False
    
    def list_threads(self) -> list[Thread]:
        return list(self._threads.values())


_thread_store: InMemoryThreadStore | None = None


def get_thread_store() -> InMemoryThreadStore:
    global _thread_store
    if _thread_store is None:
        _thread_store = InMemoryThreadStore()
    return _thread_store


__all__ = ["Message", "Thread", "InMemoryThreadStore", "get_thread_store"]