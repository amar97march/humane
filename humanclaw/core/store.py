from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from humanclaw.core.models import (
    EntityState,
    EntityType,
    Goal,
    HoldItem,
    Memory,
    MemoryType,
    ProposedAction,
    RelationshipHealth,
    TrustLevel,
    ValueSeverity,
    ValueStatement,
    Verdict,
)


class Store:
    def __init__(self, db_path: str):
        expanded = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(expanded), exist_ok=True)
        self.db_path = expanded
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def initialize(self) -> None:
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS human_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS hold_queue (
                    id TEXT PRIMARY KEY,
                    action_json TEXT NOT NULL,
                    adjusted_confidence REAL NOT NULL,
                    hold_reason TEXT NOT NULL,
                    hold_source TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    resolution TEXT
                );

                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    sentiment_score REAL NOT NULL DEFAULT 0.0,
                    grudge_score REAL NOT NULL DEFAULT 0.0,
                    trust_level TEXT NOT NULL DEFAULT 'neutral',
                    relationship_health TEXT NOT NULL DEFAULT 'stable',
                    disclosure_threshold REAL NOT NULL DEFAULT 0.7,
                    interaction_count INTEGER NOT NULL DEFAULT 0,
                    last_interaction_at REAL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    expected_value REAL NOT NULL DEFAULT 1.0,
                    remaining_effort REAL NOT NULL DEFAULT 1.0,
                    progress_velocity REAL NOT NULL DEFAULT 0.0,
                    relevance_decay REAL NOT NULL DEFAULT 1.0,
                    milestones_total INTEGER NOT NULL DEFAULT 0,
                    milestones_completed INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    last_evaluated_at REAL,
                    status TEXT NOT NULL DEFAULT 'active'
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    relevance_score REAL NOT NULL DEFAULT 1.0,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL,
                    archived INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS values_table (
                    id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    behavioral_pattern TEXT NOT NULL,
                    violation_examples_json TEXT NOT NULL DEFAULT '[]',
                    honoring_examples_json TEXT NOT NULL DEFAULT '[]',
                    severity TEXT NOT NULL DEFAULT 'soft'
                );

                CREATE TABLE IF NOT EXISTS interactions (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    sentiment REAL NOT NULL,
                    content_summary TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
                );
            """)

    # --- human_state ---

    def get(self, key: str) -> Optional[Any]:
        return self.load_state(key)

    def set(self, key: str, value: Any) -> None:
        self.save_state(key, value)

    def save_state(self, key: str, value: Any) -> None:
        serialized = json.dumps(value)
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO human_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, serialized, time.time()),
            )

    def load_state(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM human_state WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    # --- hold_queue ---

    def add_hold_item(self, item: HoldItem) -> None:
        action_data = {
            "action_type": item.action.action_type,
            "payload": item.action.payload,
            "confidence": item.action.confidence,
            "rationale": item.action.rationale,
            "source": item.action.source,
            "target_entity": item.action.target_entity,
            "created_at": item.action.created_at,
        }
        with self.conn:
            self.conn.execute(
                """INSERT INTO hold_queue
                   (id, action_json, adjusted_confidence, hold_reason, hold_source,
                    verdict, created_at, expires_at, resolved, resolution)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.id,
                    json.dumps(action_data),
                    item.adjusted_confidence,
                    item.hold_reason,
                    item.hold_source,
                    item.verdict.value,
                    item.created_at,
                    item.expires_at,
                    int(item.resolved),
                    item.resolution,
                ),
            )

    def get_hold_queue(self, include_resolved: bool = False) -> List[HoldItem]:
        if include_resolved:
            rows = self.conn.execute("SELECT * FROM hold_queue ORDER BY created_at DESC").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM hold_queue WHERE resolved = 0 ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_hold_item(row) for row in rows]

    def resolve_hold_item(self, item_id: str, resolution: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE hold_queue SET resolved = 1, resolution = ? WHERE id = ?",
                (resolution, item_id),
            )

    def _row_to_hold_item(self, row: sqlite3.Row) -> HoldItem:
        action_data = json.loads(row["action_json"])
        action = ProposedAction(
            action_type=action_data["action_type"],
            payload=action_data["payload"],
            confidence=action_data["confidence"],
            rationale=action_data["rationale"],
            source=action_data["source"],
            target_entity=action_data.get("target_entity"),
            created_at=action_data.get("created_at", 0.0),
        )
        return HoldItem(
            id=row["id"],
            action=action,
            adjusted_confidence=row["adjusted_confidence"],
            hold_reason=row["hold_reason"],
            hold_source=row["hold_source"],
            verdict=Verdict(row["verdict"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            resolved=bool(row["resolved"]),
            resolution=row["resolution"],
        )

    # --- entities ---

    def add_entity(self, entity: EntityState) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO entities
                   (entity_id, name, entity_type, sentiment_score, grudge_score,
                    trust_level, relationship_health, disclosure_threshold,
                    interaction_count, last_interaction_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity.entity_id,
                    entity.name,
                    entity.entity_type.value,
                    entity.sentiment_score,
                    entity.grudge_score,
                    entity.trust_level.value,
                    entity.relationship_health.value,
                    entity.disclosure_threshold,
                    entity.interaction_count,
                    entity.last_interaction_at,
                    entity.created_at,
                ),
            )

    def get_entity(self, entity_id: str) -> Optional[EntityState]:
        row = self.conn.execute("SELECT * FROM entities WHERE entity_id = ?", (entity_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def update_entity(self, entity: EntityState) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE entities SET
                   name=?, entity_type=?, sentiment_score=?, grudge_score=?,
                   trust_level=?, relationship_health=?, disclosure_threshold=?,
                   interaction_count=?, last_interaction_at=?
                   WHERE entity_id=?""",
                (
                    entity.name,
                    entity.entity_type.value,
                    entity.sentiment_score,
                    entity.grudge_score,
                    entity.trust_level.value,
                    entity.relationship_health.value,
                    entity.disclosure_threshold,
                    entity.interaction_count,
                    entity.last_interaction_at,
                    entity.entity_id,
                ),
            )

    def list_entities(self, entity_type: Optional[EntityType] = None) -> List[EntityState]:
        if entity_type:
            rows = self.conn.execute(
                "SELECT * FROM entities WHERE entity_type = ? ORDER BY name", (entity_type.value,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM entities ORDER BY name").fetchall()
        return [self._row_to_entity(row) for row in rows]

    def _row_to_entity(self, row: sqlite3.Row) -> EntityState:
        return EntityState(
            entity_id=row["entity_id"],
            name=row["name"],
            entity_type=EntityType(row["entity_type"]),
            sentiment_score=row["sentiment_score"],
            grudge_score=row["grudge_score"],
            trust_level=TrustLevel(row["trust_level"]),
            relationship_health=RelationshipHealth(row["relationship_health"]),
            disclosure_threshold=row["disclosure_threshold"],
            interaction_count=row["interaction_count"],
            last_interaction_at=row["last_interaction_at"],
            created_at=row["created_at"],
        )

    # --- goals ---

    def add_goal(self, goal: Goal) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO goals
                   (id, description, expected_value, remaining_effort, progress_velocity,
                    relevance_decay, milestones_total, milestones_completed,
                    created_at, last_evaluated_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    goal.id,
                    goal.description,
                    goal.expected_value,
                    goal.remaining_effort,
                    goal.progress_velocity,
                    goal.relevance_decay,
                    goal.milestones_total,
                    goal.milestones_completed,
                    goal.created_at,
                    goal.last_evaluated_at,
                    goal.status,
                ),
            )

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        row = self.conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_goal(row)

    def update_goal(self, goal: Goal) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE goals SET
                   description=?, expected_value=?, remaining_effort=?, progress_velocity=?,
                   relevance_decay=?, milestones_total=?, milestones_completed=?,
                   last_evaluated_at=?, status=?
                   WHERE id=?""",
                (
                    goal.description,
                    goal.expected_value,
                    goal.remaining_effort,
                    goal.progress_velocity,
                    goal.relevance_decay,
                    goal.milestones_total,
                    goal.milestones_completed,
                    goal.last_evaluated_at,
                    goal.status,
                    goal.id,
                ),
            )

    def list_goals(self, status: Optional[str] = None) -> List[Goal]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM goals WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
        return [self._row_to_goal(row) for row in rows]

    def _row_to_goal(self, row: sqlite3.Row) -> Goal:
        return Goal(
            id=row["id"],
            description=row["description"],
            expected_value=row["expected_value"],
            remaining_effort=row["remaining_effort"],
            progress_velocity=row["progress_velocity"],
            relevance_decay=row["relevance_decay"],
            milestones_total=row["milestones_total"],
            milestones_completed=row["milestones_completed"],
            created_at=row["created_at"],
            last_evaluated_at=row["last_evaluated_at"],
            status=row["status"],
        )

    # --- memories ---

    def add_memory(self, memory: Memory) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO memories
                   (id, memory_type, content, relevance_score, access_count,
                    pinned, created_at, last_accessed_at, archived)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory.id,
                    memory.memory_type.value,
                    memory.content,
                    memory.relevance_score,
                    memory.access_count,
                    int(memory.pinned),
                    memory.created_at,
                    memory.last_accessed_at,
                    int(memory.archived),
                ),
            )

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def update_memory(self, memory: Memory) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE memories SET
                   memory_type=?, content=?, relevance_score=?, access_count=?,
                   pinned=?, last_accessed_at=?, archived=?
                   WHERE id=?""",
                (
                    memory.memory_type.value,
                    memory.content,
                    memory.relevance_score,
                    memory.access_count,
                    int(memory.pinned),
                    memory.last_accessed_at,
                    int(memory.archived),
                    memory.id,
                ),
            )

    def list_memories(
        self,
        memory_type: Optional[MemoryType] = None,
        include_archived: bool = False,
    ) -> List[Memory]:
        conditions = []
        params: List[Any] = []

        if not include_archived:
            conditions.append("archived = 0")
        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type.value)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.conn.execute(
            f"SELECT * FROM memories {where} ORDER BY created_at DESC", params
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"],
            memory_type=MemoryType(row["memory_type"]),
            content=row["content"],
            relevance_score=row["relevance_score"],
            access_count=row["access_count"],
            pinned=bool(row["pinned"]),
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
            archived=bool(row["archived"]),
        )

    # --- events ---

    def add_event(self, event_id: str, event_type: str, engine: str, data: Dict) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO events (id, event_type, engine, data_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (event_id, event_type, engine, json.dumps(data), time.time()),
            )

    def list_events(
        self,
        limit: int = 50,
        engine: Optional[str] = None,
    ) -> List[Dict]:
        if engine:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE engine = ? ORDER BY created_at DESC LIMIT ?",
                (engine, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "engine": row["engine"],
                "data": json.loads(row["data_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # --- values ---

    def add_value(self, value: ValueStatement) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO values_table
                   (id, description, behavioral_pattern, violation_examples_json,
                    honoring_examples_json, severity)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    value.id,
                    value.description,
                    value.behavioral_pattern,
                    json.dumps(value.violation_examples),
                    json.dumps(value.honoring_examples),
                    value.severity.value,
                ),
            )

    def get_values(self) -> List[ValueStatement]:
        rows = self.conn.execute("SELECT * FROM values_table").fetchall()
        return [
            ValueStatement(
                id=row["id"],
                description=row["description"],
                behavioral_pattern=row["behavioral_pattern"],
                violation_examples=json.loads(row["violation_examples_json"]),
                honoring_examples=json.loads(row["honoring_examples_json"]),
                severity=ValueSeverity(row["severity"]),
            )
            for row in rows
        ]

    def update_value(self, value: ValueStatement) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE values_table SET
                   description=?, behavioral_pattern=?, violation_examples_json=?,
                   honoring_examples_json=?, severity=?
                   WHERE id=?""",
                (
                    value.description,
                    value.behavioral_pattern,
                    json.dumps(value.violation_examples),
                    json.dumps(value.honoring_examples),
                    value.severity.value,
                    value.id,
                ),
            )

    # --- interactions ---

    def add_interaction(
        self,
        interaction_id: str,
        entity_id: str,
        sentiment: float,
        content_summary: str,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO interactions (id, entity_id, sentiment, content_summary, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (interaction_id, entity_id, sentiment, content_summary, time.time()),
            )

    def get_interactions(
        self,
        entity_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        if entity_id:
            rows = self.conn.execute(
                "SELECT * FROM interactions WHERE entity_id = ? ORDER BY created_at DESC LIMIT ?",
                (entity_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM interactions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "entity_id": row["entity_id"],
                "sentiment": row["sentiment"],
                "content_summary": row["content_summary"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
