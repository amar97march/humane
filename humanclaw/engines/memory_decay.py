from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from humanclaw.core.config import HumanClawConfig
from humanclaw.core.models import Memory, MemoryType


class Store(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any) -> None: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


class MemoryDecayEngine:
    STORE_KEY = "memory_decay"

    DECAY_COEFFICIENTS: Dict[MemoryType, float] = {
        MemoryType.EPISODIC: 0.05,
        MemoryType.SEMANTIC: 0.005,
        MemoryType.RELATIONAL: 0.002,
        MemoryType.PROCEDURAL: 0.0005,
    }

    def __init__(
        self, config: HumanClawConfig, store: Store, event_log: EventLog
    ) -> None:
        self.config = config
        self.store = store
        self.event_log = event_log
        self._memories: Dict[str, Memory] = {}
        self._load()

    def add_memory(
        self,
        memory_type: MemoryType,
        content: str,
        pinned: bool = False,
    ) -> Memory:
        memory_id = str(uuid4())
        memory = Memory(
            id=memory_id,
            memory_type=memory_type,
            content=content,
            relevance_score=1.0,
            access_count=0,
            pinned=pinned,
            created_at=time.time(),
            last_accessed_at=time.time(),
            archived=False,
        )
        self._memories[memory_id] = memory
        self._save()
        self.event_log.log("memory_added", "memory_decay", {
            "memory_id": memory_id,
            "type": memory_type.value,
            "pinned": pinned,
        })
        return memory

    def access_memory(self, memory_id: str) -> Optional[Memory]:
        memory = self._memories.get(memory_id)
        if memory is None:
            return None

        memory.access_count += 1
        memory.last_accessed_at = time.time()

        reinforcement = 0.1 + (0.05 * min(memory.access_count, 10))
        memory.relevance_score = min(1.0, memory.relevance_score + reinforcement)

        if memory.archived:
            memory.archived = False
            self.event_log.log("memory_unarchived_by_access", "memory_decay", {
                "memory_id": memory_id,
            })

        self._save()
        return memory

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        return self._memories.get(memory_id)

    def decay_tick(self) -> None:
        now = time.time()
        archived_ids: List[str] = []

        for memory in self._memories.values():
            if memory.pinned or memory.archived:
                continue

            coefficient = self.DECAY_COEFFICIENTS.get(
                memory.memory_type, 0.01
            )

            last_access = memory.last_accessed_at or memory.created_at
            days_since = (now - last_access) / 86400

            access_bonus = math.log1p(memory.access_count) * 0.1
            effective_coeff = max(0.0001, coefficient - access_bonus * coefficient)

            memory.relevance_score *= math.exp(-effective_coeff * days_since)
            memory.relevance_score = max(0.0, min(1.0, memory.relevance_score))

            if memory.relevance_score < self.config.memory_retrieval_threshold:
                memory.archived = True
                archived_ids.append(memory.id)

        if archived_ids:
            self.event_log.log("memories_archived", "memory_decay", {
                "archived_count": len(archived_ids),
                "memory_ids": archived_ids,
            })

        self._save()

    def recall_archived(self, memory_id: str) -> Optional[Memory]:
        memory = self._memories.get(memory_id)
        if memory is None or not memory.archived:
            return memory

        memory.archived = False
        memory.relevance_score = max(0.5, memory.relevance_score)
        memory.access_count += 1
        memory.last_accessed_at = time.time()

        self._save()
        self.event_log.log("memory_recalled", "memory_decay", {
            "memory_id": memory_id,
        })
        return memory

    def search(self, query: str, include_archived: bool = False) -> List[Memory]:
        query_lower = query.lower()
        query_words = set(query_lower.split())
        results: List[Memory] = []

        for memory in self._memories.values():
            if not include_archived and memory.archived:
                continue

            content_lower = memory.content.lower()
            if query_lower in content_lower or any(w in content_lower for w in query_words):
                results.append(memory)

        results.sort(key=lambda m: m.relevance_score, reverse=True)
        return results

    def pin(self, memory_id: str) -> None:
        memory = self._memories.get(memory_id)
        if memory is None:
            return
        memory.pinned = True
        memory.archived = False
        self._save()
        self.event_log.log("memory_pinned", "memory_decay", {"memory_id": memory_id})

    def unpin(self, memory_id: str) -> None:
        memory = self._memories.get(memory_id)
        if memory is None:
            return
        memory.pinned = False
        self._save()
        self.event_log.log("memory_unpinned", "memory_decay", {"memory_id": memory_id})

    def active_memories(self) -> List[Memory]:
        return [m for m in self._memories.values() if not m.archived]

    def archived_memories(self) -> List[Memory]:
        return [m for m in self._memories.values() if m.archived]

    def _save(self) -> None:
        data: Dict[str, Dict[str, Any]] = {}
        for mid, m in self._memories.items():
            data[mid] = {
                "id": m.id,
                "memory_type": m.memory_type.value,
                "content": m.content,
                "relevance_score": m.relevance_score,
                "access_count": m.access_count,
                "pinned": m.pinned,
                "created_at": m.created_at,
                "last_accessed_at": m.last_accessed_at,
                "archived": m.archived,
            }
        self.store.set(self.STORE_KEY, {"memories": data})

    def _load(self) -> None:
        data = self.store.get(self.STORE_KEY)
        if data is None:
            return
        for mid, md in data.get("memories", {}).items():
            self._memories[mid] = Memory(
                id=md["id"],
                memory_type=MemoryType(md["memory_type"]),
                content=md["content"],
                relevance_score=md.get("relevance_score", 1.0),
                access_count=md.get("access_count", 0),
                pinned=md.get("pinned", False),
                created_at=md.get("created_at", time.time()),
                last_accessed_at=md.get("last_accessed_at"),
                archived=md.get("archived", False),
            )
