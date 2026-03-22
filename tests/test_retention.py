"""Tests for the RetentionManager — automated data cleanup policies."""

import time
import pytest
from uuid import uuid4

from humane.core.config import HumaneConfig
from humane.core.models import (
    HoldItem, Memory, MemoryType, ProposedAction, Verdict,
)
from humane.core.store import Store
from humane.retention import RetentionManager


@pytest.fixture
def config():
    config = HumaneConfig()
    config.retention_conversations_days = 90
    config.retention_events_days = 180
    config.retention_memory_archive_days = 30
    config.retention_holds_days = 30
    return config


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_retention.db")
    store = Store(db_path)
    store.initialize()
    return store


@pytest.fixture
def retention(tmp_db, config):
    return RetentionManager(tmp_db, config)


def _add_old_conversation(store, days_old):
    """Insert a conversation that is days_old days in the past."""
    ts = time.time() - (days_old * 86400)
    cid = str(uuid4())
    store.conn.execute(
        "INSERT INTO conversations (id, chat_id, user_id, role, content, sentiment, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cid, 1, 1, "user", "old message", 0.0, ts),
    )
    store.conn.commit()
    return cid


def _add_old_event(store, days_old):
    ts = time.time() - (days_old * 86400)
    eid = str(uuid4())
    store.conn.execute(
        "INSERT INTO events (id, event_type, engine, data_json, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (eid, "test", "test", "{}", ts),
    )
    store.conn.commit()
    return eid


def _add_resolved_hold(store, days_old):
    ts = time.time() - (days_old * 86400)
    action = ProposedAction(
        action_type="test", payload={}, confidence=0.5,
        rationale="test", source="test",
    )
    hold = HoldItem(
        id=str(uuid4()), action=action,
        adjusted_confidence=0.5, hold_reason="test",
        hold_source="test", verdict=Verdict.HOLD,
        created_at=ts, resolved=True, resolution="approved",
    )
    store.add_hold_item(hold)
    # Mark as resolved
    store.resolve_hold_item(hold.id, "approved")
    return hold.id


class TestApplyPolicies:
    def test_deletes_old_conversations(self, retention, tmp_db):
        _add_old_conversation(tmp_db, 100)  # older than 90 days
        _add_old_conversation(tmp_db, 50)   # within retention

        result = retention.apply_policies()
        assert result["conversations_deleted"] == 1

        # Verify the recent one still exists
        count = tmp_db.conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()["cnt"]
        assert count == 1

    def test_deletes_old_events(self, retention, tmp_db):
        _add_old_event(tmp_db, 200)  # older than 180 days
        _add_old_event(tmp_db, 10)   # within retention

        result = retention.apply_policies()
        assert result["events_deleted"] == 1

    def test_deletes_resolved_holds(self, retention, tmp_db):
        _add_resolved_hold(tmp_db, 40)  # older than 30 days
        _add_resolved_hold(tmp_db, 5)   # within retention

        result = retention.apply_policies()
        assert result["holds_deleted"] == 1


class TestDryRun:
    def test_dry_run_doesnt_delete(self, retention, tmp_db):
        _add_old_conversation(tmp_db, 100)
        _add_old_event(tmp_db, 200)

        preview = retention.dry_run()
        assert preview["conversations_to_delete"] == 1
        assert preview["events_to_delete"] == 1

        # Verify nothing was actually deleted
        conv_count = tmp_db.conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()["cnt"]
        event_count = tmp_db.conn.execute("SELECT COUNT(*) as cnt FROM events").fetchone()["cnt"]
        assert conv_count == 1
        assert event_count == 1


class TestGetRetentionStats:
    def test_returns_counts(self, retention, tmp_db):
        _add_old_conversation(tmp_db, 10)
        _add_old_event(tmp_db, 10)

        stats = retention.get_retention_stats()
        assert "total_conversations" in stats
        assert "total_events" in stats
        assert "total_memories" in stats
        assert "total_holds" in stats
        assert stats["total_conversations"] == 1
        assert stats["total_events"] == 1


class TestCustomRetentionDays:
    def test_custom_retention_days_respected(self, tmp_db):
        config = HumaneConfig()
        config.retention_conversations_days = 10  # Very short retention
        config.retention_events_days = 10
        config.retention_memory_archive_days = 5
        config.retention_holds_days = 5
        mgr = RetentionManager(tmp_db, config)

        _add_old_conversation(tmp_db, 15)  # Should be deleted with 10-day retention
        _add_old_conversation(tmp_db, 5)   # Should survive

        result = mgr.apply_policies()
        assert result["conversations_deleted"] == 1


class TestDisabledRetention:
    def test_disabled_retention_preserves_all(self, tmp_db):
        """When retention days are very large, nothing should be deleted."""
        config = HumaneConfig()
        config.retention_conversations_days = 999999
        config.retention_events_days = 999999
        config.retention_memory_archive_days = 999999
        config.retention_holds_days = 999999
        mgr = RetentionManager(tmp_db, config)

        _add_old_conversation(tmp_db, 100)
        _add_old_event(tmp_db, 200)

        result = mgr.apply_policies()
        assert result["conversations_deleted"] == 0
        assert result["events_deleted"] == 0
        assert result["holds_deleted"] == 0


class TestRetentionArchivesMemories:
    def test_archives_stale_memories(self, retention, tmp_db, config):
        # Add a non-pinned memory with low relevance created long ago
        ts = time.time() - (60 * 86400)
        mem = Memory(
            id=str(uuid4()),
            memory_type=MemoryType.EPISODIC,
            content="Old memory content",
            relevance_score=0.1,  # Below threshold
            pinned=False,
            created_at=ts,
            archived=False,
        )
        tmp_db.add_memory(mem)

        result = retention.apply_policies()
        assert result["memories_archived"] >= 1

        # Verify it was archived, not deleted
        stored = tmp_db.get_memory(mem.id)
        assert stored is not None
        assert stored.archived is True
