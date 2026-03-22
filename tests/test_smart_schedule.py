"""Tests for the SmartScheduler — best-time-to-contact engine."""

import time
import pytest
from datetime import datetime
from uuid import uuid4

from humane.core.config import HumaneConfig
from humane.core.models import EntityState, EntityType
from humane.core.store import Store
from humane.smart_schedule import SmartScheduler


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_schedule.db")
    store = Store(db_path)
    store.initialize()
    return store


@pytest.fixture
def scheduler(tmp_db):
    return SmartScheduler(tmp_db)


def _add_entity(store, entity_id="e1", name="Alice"):
    entity = EntityState(
        entity_id=entity_id, name=name,
        entity_type=EntityType.CLIENT,
        created_at=time.time() - 86400 * 30,
    )
    store.add_entity(entity)
    return entity_id


def _add_interactions(store, entity_id, count=5, base_days_ago=10):
    """Add interactions spread over time with varying sentiments."""
    now = time.time()
    for i in range(count):
        ts = now - (base_days_ago - i) * 86400
        sentiment = 0.3 + (i * 0.1)
        store.add_interaction(
            interaction_id=str(uuid4()),
            entity_id=entity_id,
            sentiment=sentiment,
            content_summary=f"Interaction {i}",
        )
        # Override the created_at timestamp directly
        store.conn.execute(
            "UPDATE interactions SET created_at = ? WHERE id = (SELECT id FROM interactions ORDER BY rowid DESC LIMIT 1)",
            (ts,),
        )
    store.conn.commit()


class TestAnalyzeResponsePatterns:
    def test_returns_expected_fields(self, scheduler, tmp_db):
        eid = _add_entity(tmp_db)
        _add_interactions(tmp_db, eid)

        result = scheduler.analyze_response_patterns(eid)
        expected_fields = {
            "entity_id", "entity_name", "best_day_of_week", "best_hour",
            "avg_response_time_hours", "interaction_frequency_days",
            "last_contact_days_ago", "suggested_next_contact", "total_interactions",
        }
        assert expected_fields.issubset(result.keys())

    def test_entity_not_found(self, scheduler):
        result = scheduler.analyze_response_patterns("nonexistent")
        assert "error" in result

    def test_entity_with_no_interactions(self, scheduler, tmp_db):
        eid = _add_entity(tmp_db)
        result = scheduler.analyze_response_patterns(eid)
        assert result["total_interactions"] == 0
        assert result["best_day_of_week"] == "N/A"


class TestBestDayOfWeek:
    def test_best_day_is_valid_day_name(self, scheduler, tmp_db):
        eid = _add_entity(tmp_db)
        _add_interactions(tmp_db, eid, count=10, base_days_ago=20)

        result = scheduler.analyze_response_patterns(eid)
        valid_days = {"Monday", "Tuesday", "Wednesday", "Thursday",
                      "Friday", "Saturday", "Sunday", "N/A"}
        assert result["best_day_of_week"] in valid_days


class TestSuggestedNextContact:
    def test_suggested_next_contact_is_in_future(self, scheduler, tmp_db):
        eid = _add_entity(tmp_db)
        _add_interactions(tmp_db, eid, count=5)

        result = scheduler.analyze_response_patterns(eid)
        suggested = result["suggested_next_contact"]
        # Parse ISO format
        suggested_dt = datetime.fromisoformat(suggested)
        assert suggested_dt > datetime.now()


class TestGetScheduleForAll:
    def test_returns_sorted_by_urgency(self, scheduler, tmp_db):
        # Entity with old interactions (overdue)
        eid1 = _add_entity(tmp_db, "e_overdue", "Overdue Contact")
        _add_interactions(tmp_db, eid1, count=3, base_days_ago=30)

        # Entity with recent interactions (not overdue)
        eid2 = _add_entity(tmp_db, "e_recent", "Recent Contact")
        _add_interactions(tmp_db, eid2, count=3, base_days_ago=3)

        results = scheduler.get_schedule_for_all()
        assert len(results) >= 2
        # First result should have higher urgency (overdue)
        urgency_order = {"overdue": 0, "due_soon": 1, "scheduled": 2}
        for i in range(len(results) - 1):
            u1 = urgency_order.get(results[i]["urgency"], 3)
            u2 = urgency_order.get(results[i + 1]["urgency"], 3)
            assert u1 <= u2

    def test_empty_store_returns_empty_list(self, scheduler):
        results = scheduler.get_schedule_for_all()
        assert results == []


class TestEntityNoInteractions:
    def test_no_interactions_handled_gracefully(self, scheduler, tmp_db):
        eid = _add_entity(tmp_db, "e_no_interact", "No Interactions")
        result = scheduler.analyze_response_patterns(eid)
        assert result["total_interactions"] == 0
        assert "error" not in result
        assert result["avg_response_time_hours"] == 0.0
