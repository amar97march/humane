"""Data retention policies — automated cleanup of old conversations, events, memories, and holds."""

from __future__ import annotations

import logging
import time
from typing import Dict

from humane.core.config import HumaneConfig
from humane.core.store import Store

logger = logging.getLogger("humane.retention")

# Seconds per day
_DAY = 86400.0


class RetentionManager:
    """Applies configurable data retention policies to the store."""

    def __init__(self, store: Store, config: HumaneConfig):
        self.store = store
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_policies(self) -> Dict:
        """Run all retention rules and return counts of deleted/archived items."""
        results: Dict[str, int] = {}
        now = time.time()

        results["conversations_deleted"] = self._delete_old_conversations(now)
        results["events_deleted"] = self._delete_old_events(now)
        results["memories_archived"] = self._archive_stale_memories(now)
        results["holds_deleted"] = self._delete_resolved_holds(now)

        logger.info(
            "Retention applied: %d conversations, %d events deleted; "
            "%d memories archived; %d holds deleted",
            results["conversations_deleted"],
            results["events_deleted"],
            results["memories_archived"],
            results["holds_deleted"],
        )

        return results

    def get_retention_stats(self) -> Dict:
        """Return counts of data that currently exist in each category."""
        conn = self.store.conn
        stats: Dict[str, int] = {}

        stats["total_conversations"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM conversations"
        ).fetchone()["cnt"]

        stats["total_events"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM events"
        ).fetchone()["cnt"]

        stats["total_memories"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM memories"
        ).fetchone()["cnt"]

        stats["archived_memories"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM memories WHERE archived = 1"
        ).fetchone()["cnt"]

        stats["total_holds"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM hold_queue"
        ).fetchone()["cnt"]

        stats["resolved_holds"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM hold_queue WHERE resolved = 1"
        ).fetchone()["cnt"]

        return stats

    def dry_run(self) -> Dict:
        """Show what would be affected by current policies without deleting."""
        now = time.time()
        preview: Dict[str, int] = {}

        conv_cutoff = now - (self.config.retention_conversations_days * _DAY)
        preview["conversations_to_delete"] = self.store.conn.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE created_at < ?",
            (conv_cutoff,),
        ).fetchone()["cnt"]

        events_cutoff = now - (self.config.retention_events_days * _DAY)
        preview["events_to_delete"] = self.store.conn.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE created_at < ?",
            (events_cutoff,),
        ).fetchone()["cnt"]

        mem_cutoff = now - (self.config.retention_memory_archive_days * _DAY)
        threshold = self.config.memory_retrieval_threshold
        preview["memories_to_archive"] = self.store.conn.execute(
            "SELECT COUNT(*) as cnt FROM memories "
            "WHERE archived = 0 AND pinned = 0 AND relevance_score < ? AND created_at < ?",
            (threshold, mem_cutoff),
        ).fetchone()["cnt"]

        holds_cutoff = now - (self.config.retention_holds_days * _DAY)
        preview["holds_to_delete"] = self.store.conn.execute(
            "SELECT COUNT(*) as cnt FROM hold_queue WHERE resolved = 1 AND created_at < ?",
            (holds_cutoff,),
        ).fetchone()["cnt"]

        return preview

    # ------------------------------------------------------------------
    # Internal policy implementations
    # ------------------------------------------------------------------

    def _delete_old_conversations(self, now: float) -> int:
        cutoff = now - (self.config.retention_conversations_days * _DAY)
        with self.store.conn:
            cursor = self.store.conn.execute(
                "DELETE FROM conversations WHERE created_at < ?", (cutoff,)
            )
            return cursor.rowcount

    def _delete_old_events(self, now: float) -> int:
        cutoff = now - (self.config.retention_events_days * _DAY)
        with self.store.conn:
            cursor = self.store.conn.execute(
                "DELETE FROM events WHERE created_at < ?", (cutoff,)
            )
            return cursor.rowcount

    def _archive_stale_memories(self, now: float) -> int:
        cutoff = now - (self.config.retention_memory_archive_days * _DAY)
        threshold = self.config.memory_retrieval_threshold
        with self.store.conn:
            cursor = self.store.conn.execute(
                "UPDATE memories SET archived = 1 "
                "WHERE archived = 0 AND pinned = 0 AND relevance_score < ? AND created_at < ?",
                (threshold, cutoff),
            )
            return cursor.rowcount

    def _delete_resolved_holds(self, now: float) -> int:
        cutoff = now - (self.config.retention_holds_days * _DAY)
        with self.store.conn:
            cursor = self.store.conn.execute(
                "DELETE FROM hold_queue WHERE resolved = 1 AND created_at < ?",
                (cutoff,),
            )
            return cursor.rowcount
