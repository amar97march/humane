"""Tests for the DailyDigest — morning summary generation."""

import time
import pytest
from unittest.mock import MagicMock, PropertyMock, patch

from humane.core.config import HumaneConfig
from humane.core.models import (
    EntityState, EntityType, Goal, Memory, MemoryType,
    RelationshipHealth, TrustLevel,
)
from humane.digest import DailyDigest


@pytest.fixture
def config():
    return HumaneConfig()


@pytest.fixture
def conductor_mock(config):
    conductor = MagicMock()
    conductor.config = config

    # Goal engine mock
    conductor.goal_engine.active_goals.return_value = []
    conductor.goal_engine.compute_roi.return_value = 0.5

    # Hold queue
    conductor.get_hold_queue.return_value = []

    # Relational engine
    conductor.relational.list_entities.return_value = []

    # Event log
    conductor.event_log.recent.return_value = []

    # Memory decay
    conductor.memory_decay.active_memories.return_value = []

    # Human state
    conductor.human_state.tick.return_value = None
    conductor.get_state_snapshot.return_value = {
        "energy": 0.8,
        "mood": 0.2,
        "fatigue": 0.3,
        "boredom": 0.1,
        "focus": 0.7,
        "social_load": 0.2,
    }
    return conductor


@pytest.fixture
def digest(conductor_mock, config):
    return DailyDigest(conductor_mock, config)


class TestDigestGenerate:
    def test_generate_returns_all_sections(self, digest):
        result = digest.generate()
        expected_keys = {
            "generated_at", "generated_at_iso", "stalling_goals",
            "pending_holds", "neglected_entities", "sentiment_alerts",
            "anomalies", "memory_decay_warnings", "impulse_summary",
            "state_summary",
        }
        assert expected_keys.issubset(result.keys())

    def test_generated_at_is_recent(self, digest):
        result = digest.generate()
        assert abs(result["generated_at"] - time.time()) < 5

    def test_generated_at_iso_is_string(self, digest):
        result = digest.generate()
        assert isinstance(result["generated_at_iso"], str)
        assert "T" in result["generated_at_iso"]


class TestFormatText:
    def test_format_text_produces_readable_string(self, digest):
        text = digest.format_text()
        assert isinstance(text, str)
        assert "Daily Digest" in text
        assert "STATE" in text
        assert "STALLING GOALS" in text
        assert "PENDING HOLDS" in text
        assert "NEGLECTED CONTACTS" in text
        assert "SENTIMENT ALERTS" in text

    def test_format_text_includes_state_values(self, digest):
        text = digest.format_text()
        assert "Energy:" in text
        assert "Mood:" in text
        assert "Fatigue:" in text
        assert "Focus:" in text


class TestStallingGoals:
    def test_stalling_goal_detected(self, digest, conductor_mock):
        now = time.time()
        stale_goal = Goal(
            id="g1",
            description="Close the design deal",
            expected_value=1.0,
            remaining_effort=0.8,
            progress_velocity=0.0,
            created_at=now - (10 * 86400),
            last_evaluated_at=now - (10 * 86400),
            status="active",
        )
        conductor_mock.goal_engine.active_goals.return_value = [stale_goal]
        conductor_mock.goal_engine.compute_roi.return_value = 0.1

        result = digest.generate()
        assert len(result["stalling_goals"]) == 1
        assert result["stalling_goals"][0]["id"] == "g1"
        assert "low ROI" in result["stalling_goals"][0]["reasons"][0]

    def test_no_stalling_when_goals_progressing(self, digest, conductor_mock):
        now = time.time()
        active_goal = Goal(
            id="g2",
            description="Active project",
            created_at=now - 86400,
            last_evaluated_at=now - 3600,
            status="active",
        )
        conductor_mock.goal_engine.active_goals.return_value = [active_goal]
        conductor_mock.goal_engine.compute_roi.return_value = 0.9

        result = digest.generate()
        assert len(result["stalling_goals"]) == 0


class TestNeglectedEntities:
    def test_neglected_entity_detected(self, digest, conductor_mock):
        now = time.time()
        old_entity = EntityState(
            entity_id="e1",
            name="Old Contact",
            entity_type=EntityType.CLIENT,
            last_interaction_at=now - (20 * 86400),
            created_at=now - (30 * 86400),
        )
        conductor_mock.relational.list_entities.return_value = [old_entity]

        result = digest.generate()
        assert len(result["neglected_entities"]) == 1
        assert result["neglected_entities"][0]["entity_id"] == "e1"
        assert result["neglected_entities"][0]["days_since_contact"] >= 14


class TestSentimentAlerts:
    def test_negative_sentiment_alert(self, digest, conductor_mock):
        entity = EntityState(
            entity_id="e2",
            name="Unhappy Client",
            entity_type=EntityType.CLIENT,
            sentiment_score=-0.5,
            trust_level=TrustLevel.CAUTIOUS,
            relationship_health=RelationshipHealth.FRAGILE,
        )
        conductor_mock.relational.list_entities.return_value = [entity]

        result = digest.generate()
        assert len(result["sentiment_alerts"]) == 1
        assert result["sentiment_alerts"][0]["sentiment_score"] == -0.5


class TestEmptyDatabase:
    def test_empty_database_returns_empty_sections(self, digest):
        result = digest.generate()
        assert result["stalling_goals"] == []
        assert result["pending_holds"]["count"] == 0
        assert result["neglected_entities"] == []
        assert result["sentiment_alerts"] == []
        assert result["anomalies"] == []
        assert result["memory_decay_warnings"] == []
        assert result["impulse_summary"]["total"] == 0
