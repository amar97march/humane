"""Tests for the PredictiveInsights engine."""

import time
import pytest
from unittest.mock import MagicMock

from humane.core.models import (
    EntityState, EntityType, Goal, RelationshipHealth, TrustLevel,
)
from humane.insights import PredictiveInsights


@pytest.fixture
def conductor_mock():
    conductor = MagicMock()
    # Relational engine
    conductor.relational.list_entities.return_value = []
    conductor.relational._interaction_log = {}
    # Goal engine
    conductor.goal_engine.active_goals.return_value = []
    conductor.goal_engine.compute_roi.return_value = 0.5
    # Human state
    conductor.human_state.social_load = 0.3
    conductor.human_state.fatigue = 0.3
    conductor.human_state.energy = 0.8
    conductor.human_state.boredom = 0.2
    # Anomaly detector
    conductor.anomaly_detector._baselines = {}
    return conductor


@pytest.fixture
def insights(conductor_mock):
    return PredictiveInsights(conductor_mock)


class TestGenerateInsights:
    def test_returns_list_of_dicts(self, insights):
        result = insights.generate_insights()
        assert isinstance(result, list)

    def test_each_insight_has_required_fields(self, insights, conductor_mock):
        # Set up a condition that generates an insight
        conductor_mock.human_state.fatigue = 0.85
        result = insights.generate_insights()
        assert len(result) > 0
        for insight in result:
            assert "type" in insight
            assert "severity" in insight
            assert "title" in insight
            assert "description" in insight
            assert "action_suggestion" in insight

    def test_empty_database_returns_empty_list(self, insights):
        result = insights.generate_insights()
        assert result == []


class TestSentimentDecline:
    def test_sentiment_decline_detected(self, insights, conductor_mock):
        entity = EntityState(
            entity_id="e1", name="Alice",
            entity_type=EntityType.CLIENT,
        )
        conductor_mock.relational.list_entities.return_value = [entity]
        now = time.time()
        conductor_mock.relational._interaction_log = {
            "e1": [
                {"timestamp": now - 86400 * 10, "sentiment": 0.8},
                {"timestamp": now - 86400 * 9, "sentiment": 0.7},
                {"timestamp": now - 86400 * 2, "sentiment": 0.2},
                {"timestamp": now - 86400 * 1, "sentiment": 0.1},
            ]
        }

        result = insights.generate_insights()
        decline_insights = [i for i in result if i["type"] == "sentiment_decline"]
        assert len(decline_insights) >= 1
        assert decline_insights[0]["entity_id"] == "e1"


class TestGoalStalling:
    def test_goal_stalling_detected(self, insights, conductor_mock):
        now = time.time()
        stale_goal = Goal(
            id="g1",
            description="Build the new dashboard",
            progress_velocity=0.0,
            created_at=now - (10 * 86400),
            last_evaluated_at=now - (10 * 86400),
            status="active",
        )
        conductor_mock.goal_engine.active_goals.return_value = [stale_goal]
        conductor_mock.goal_engine.compute_roi.return_value = 0.15

        result = insights.generate_insights()
        stalling = [i for i in result if i["type"] == "goal_stalling"]
        assert len(stalling) >= 1
        assert "stalling" in stalling[0]["title"].lower()


class TestCommunicationGap:
    def test_communication_gap_detected(self, insights, conductor_mock):
        now = time.time()
        entity = EntityState(
            entity_id="e2", name="Bob",
            entity_type=EntityType.PROSPECT,
            last_interaction_at=now - (30 * 86400),
        )
        conductor_mock.relational.list_entities.return_value = [entity]
        # Regular daily interactions then a long gap
        conductor_mock.relational._interaction_log = {
            "e2": [
                {"timestamp": now - 86400 * 35, "sentiment": 0.5},
                {"timestamp": now - 86400 * 34, "sentiment": 0.4},
                {"timestamp": now - 86400 * 33, "sentiment": 0.5},
                {"timestamp": now - 86400 * 30, "sentiment": 0.3},
            ]
        }

        result = insights.generate_insights()
        gaps = [i for i in result if i["type"] == "communication_gap"]
        assert len(gaps) >= 1


class TestOverloadWarning:
    def test_fatigue_overload_detected(self, insights, conductor_mock):
        conductor_mock.human_state.fatigue = 0.85

        result = insights.generate_insights()
        overload = [i for i in result if i["type"] == "overload_warning"]
        assert len(overload) >= 1
        assert "fatigue" in overload[0]["title"].lower()

    def test_social_overload_detected(self, insights, conductor_mock):
        conductor_mock.human_state.social_load = 0.9

        result = insights.generate_insights()
        overload = [i for i in result if i["type"] == "overload_warning"]
        assert len(overload) >= 1
        assert "social" in overload[0]["title"].lower()


class TestBoredomOpportunity:
    def test_boredom_opportunity_detected(self, insights, conductor_mock):
        conductor_mock.human_state.boredom = 0.75

        result = insights.generate_insights()
        boredom = [i for i in result if i["type"] == "boredom_opportunity"]
        assert len(boredom) == 1
        assert boredom[0]["severity"] == "info"

    def test_no_boredom_when_low(self, insights, conductor_mock):
        conductor_mock.human_state.boredom = 0.3

        result = insights.generate_insights()
        boredom = [i for i in result if i["type"] == "boredom_opportunity"]
        assert len(boredom) == 0


class TestInsightSorting:
    def test_insights_sorted_by_severity(self, insights, conductor_mock):
        # Create conditions for multiple severities
        conductor_mock.human_state.fatigue = 0.9   # critical
        conductor_mock.human_state.boredom = 0.75  # info

        result = insights.generate_insights()
        if len(result) >= 2:
            severity_order = {"critical": 0, "warning": 1, "info": 2}
            for i in range(len(result) - 1):
                assert severity_order.get(result[i]["severity"], 3) <= \
                       severity_order.get(result[i + 1]["severity"], 3)
