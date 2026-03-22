"""Humane Agent-to-Agent Communication — messaging layer for multi-agent collaboration."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from uuid import uuid4

from humane.multi import AgentRegistry
from humane.core.store import Store


VALID_MESSAGE_TYPES = {
    "task_handoff",
    "info_share",
    "goal_update",
    "entity_share",
    "alert",
}


@dataclass
class AgentMessage:
    """A single inter-agent message."""

    id: str
    from_agent_id: str
    to_agent_id: str
    message_type: str
    content: str
    timestamp: float
    metadata: dict = field(default_factory=dict)
    read: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_agent_id": self.from_agent_id,
            "to_agent_id": self.to_agent_id,
            "message_type": self.message_type,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "read": self.read,
        }


def _init_agent_messages_table(store: Store) -> None:
    """Create the agent_messages table if it does not exist."""
    with store.conn:
        store.conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                id TEXT PRIMARY KEY,
                from_agent_id TEXT NOT NULL,
                to_agent_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                read INTEGER NOT NULL DEFAULT 0
            )
        """)
        store.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_messages_to
                ON agent_messages(to_agent_id, read, timestamp DESC)
        """)


class AgentCommunicator:
    """Handles inter-agent messaging, entity/goal sharing, and task hand-offs."""

    def __init__(self, registry: AgentRegistry, store: Store):
        self.registry = registry
        self.store = store
        _init_agent_messages_table(store)

    # ------------------------------------------------------------------
    # Core messaging
    # ------------------------------------------------------------------

    def send(
        self,
        from_id: str,
        to_id: str,
        message_type: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Send a message from one agent to another.  Returns the message id."""
        if message_type not in VALID_MESSAGE_TYPES:
            raise ValueError(
                f"Invalid message_type '{message_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_MESSAGE_TYPES))}"
            )
        # Validate agents exist
        self.registry.get_agent(from_id)
        self.registry.get_agent(to_id)

        msg_id = str(uuid4())[:12]
        now = time.time()
        meta = metadata or {}

        with self.store.conn:
            self.store.conn.execute(
                """INSERT INTO agent_messages
                   (id, from_agent_id, to_agent_id, message_type, content,
                    timestamp, metadata_json, read)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (msg_id, from_id, to_id, message_type, content, now, json.dumps(meta)),
            )
        return msg_id

    def get_inbox(
        self, agent_id: str, unread_only: bool = True
    ) -> list[AgentMessage]:
        """Return messages addressed to *agent_id*."""
        if unread_only:
            rows = self.store.conn.execute(
                "SELECT * FROM agent_messages WHERE to_agent_id = ? AND read = 0 "
                "ORDER BY timestamp DESC",
                (agent_id,),
            ).fetchall()
        else:
            rows = self.store.conn.execute(
                "SELECT * FROM agent_messages WHERE to_agent_id = ? "
                "ORDER BY timestamp DESC",
                (agent_id,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def mark_read(self, message_id: str) -> None:
        """Mark a single message as read."""
        with self.store.conn:
            self.store.conn.execute(
                "UPDATE agent_messages SET read = 1 WHERE id = ?", (message_id,)
            )

    def broadcast(
        self,
        from_id: str,
        message_type: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> list[str]:
        """Send *content* to every registered agent (except the sender).

        Returns a list of generated message ids.
        """
        agents = self.registry.list_agents()
        ids: list[str] = []
        for agent in agents:
            aid = agent["id"]
            if aid == from_id:
                continue
            mid = self.send(from_id, aid, message_type, content, metadata)
            ids.append(mid)
        return ids

    # ------------------------------------------------------------------
    # High-level collaboration helpers
    # ------------------------------------------------------------------

    def share_entity(self, from_id: str, to_id: str, entity_id: str) -> None:
        """Copy an entity from *from_id*'s store into *to_id*'s store and
        send a notification message."""
        src = self.registry.get_agent(from_id)
        dst = self.registry.get_agent(to_id)
        src_store: Store = src["conductor"].store
        dst_store: Store = dst["conductor"].store

        entity = src_store.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Entity '{entity_id}' not found in agent '{from_id}'")

        # Upsert into destination
        existing = dst_store.get_entity(entity_id)
        if existing is None:
            dst_store.add_entity(entity)
        else:
            dst_store.update_entity(entity)

        # Notify
        self.send(
            from_id,
            to_id,
            "entity_share",
            f"Shared entity '{entity.name}' ({entity_id})",
            metadata={"entity_id": entity_id, "entity_name": entity.name},
        )

    def share_goal(self, from_id: str, to_id: str, goal_id: str) -> None:
        """Copy a goal from *from_id*'s store into *to_id*'s store and
        send a notification message."""
        src = self.registry.get_agent(from_id)
        dst = self.registry.get_agent(to_id)
        src_store: Store = src["conductor"].store
        dst_store: Store = dst["conductor"].store

        goal = src_store.get_goal(goal_id)
        if goal is None:
            raise KeyError(f"Goal '{goal_id}' not found in agent '{from_id}'")

        existing = dst_store.get_goal(goal_id)
        if existing is None:
            dst_store.add_goal(goal)
        else:
            dst_store.update_goal(goal)

        self.send(
            from_id,
            to_id,
            "goal_update",
            f"Shared goal '{goal.description}' ({goal_id})",
            metadata={"goal_id": goal_id, "goal_description": goal.description},
        )

    def handoff_task(self, from_id: str, to_id: str, action: dict) -> None:
        """Transfer a held action from one agent to another.

        *action* should be a dict with at least ``action_type`` and ``payload``.
        """
        self.registry.get_agent(from_id)
        self.registry.get_agent(to_id)

        self.send(
            from_id,
            to_id,
            "task_handoff",
            f"Task hand-off: {action.get('action_type', 'unknown')}",
            metadata={"action": action},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_message(row) -> AgentMessage:
        return AgentMessage(
            id=row["id"],
            from_agent_id=row["from_agent_id"],
            to_agent_id=row["to_agent_id"],
            message_type=row["message_type"],
            content=row["content"],
            timestamp=row["timestamp"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            read=bool(row["read"]),
        )
