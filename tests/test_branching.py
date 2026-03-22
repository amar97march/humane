"""Tests for the ConversationBranch — what-if simulation engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from humane.branching import ConversationBranch
from humane.core.config import HumaneConfig
from humane.core.models import (
    EvaluationResult, GateResult, ProposedAction, Verdict,
)


@pytest.fixture
def conductor_mock():
    conductor = MagicMock()
    conductor.config = HumaneConfig()
    conductor.get_state_snapshot.return_value = {
        "energy": 0.8,
        "mood": 0.2,
        "fatigue": 0.3,
        "boredom": 0.1,
        "focus": 0.7,
        "social_load": 0.2,
    }
    conductor.human_state.energy = 0.8
    conductor.human_state.mood = 0.2
    conductor.human_state.fatigue = 0.3
    conductor.human_state.boredom = 0.1
    conductor.human_state.focus = 0.7
    conductor.human_state.social_load = 0.2

    # Gate stack returns PROCEED by default
    gate = GateResult(engine="values_boundary", verdict=Verdict.PROCEED, score=0.9, reason="ok")
    eval_result = EvaluationResult(
        action=ProposedAction("test", {}, 0.8, "test", "simulation"),
        final_verdict=Verdict.PROCEED,
        gate_results=[gate],
        hold_item=None,
        audit_trail=["State tick", "ALL GATES PASSED"],
    )
    conductor.evaluate.return_value = eval_result
    conductor.get_hold_queue.return_value = []

    # Relational engine
    conductor.relational.list_entities.return_value = []

    # Memory engine
    conductor.memory_decay.search.return_value = []

    # Goal engine
    conductor.goal_engine.active_goals.return_value = []

    # Store
    conductor.store.resolve_hold_item.return_value = None

    return conductor


@pytest.fixture
def branch(conductor_mock):
    return ConversationBranch(conductor_mock, conversation_engine=None)


@pytest.mark.asyncio
class TestSimulate:
    async def test_simulate_returns_all_expected_fields(self, branch):
        result = await branch.simulate("Hello, how are you?")
        expected_keys = {
            "input", "predicted_sentiment", "state_changes",
            "related_context", "gate_result", "predicted_response",
            "entities_affected",
        }
        assert expected_keys.issubset(result.keys())

    async def test_state_changes_computed(self, branch):
        result = await branch.simulate("This is great news!")
        assert "state_changes" in result
        state = result["state_changes"]
        # Should have predicted state deltas
        assert "energy_delta" in state or "predicted_state" in state

    async def test_gate_result_has_verdict(self, branch):
        result = await branch.simulate("Send a risky message")
        gate = result["gate_result"]
        assert "verdict" in gate
        assert gate["verdict"] in ("proceed", "hold", "defer")

    async def test_simulation_doesnt_persist_state(self, branch, conductor_mock):
        """Verify state is not changed by simulation."""
        state_before = conductor_mock.get_state_snapshot()
        await branch.simulate("Test message that should not persist")
        state_after = conductor_mock.get_state_snapshot()
        assert state_before == state_after


@pytest.mark.asyncio
class TestCompare:
    async def test_compare_returns_list_of_results(self, branch):
        results = await branch.compare([
            "I'm very happy with the progress",
            "This is terrible and I'm angry",
        ])
        assert isinstance(results, list)
        assert len(results) == 2
        for result in results:
            assert "input" in result
            assert "predicted_sentiment" in result
            assert "gate_result" in result


@pytest.mark.asyncio
class TestHeuristicSentiment:
    async def test_positive_message_sentiment(self, branch):
        result = await branch.simulate("Thank you, this is great and wonderful!")
        assert result["predicted_sentiment"] > 0

    async def test_negative_message_sentiment(self, branch):
        result = await branch.simulate("I hate this terrible awful experience")
        assert result["predicted_sentiment"] < 0

    async def test_neutral_message_sentiment(self, branch):
        result = await branch.simulate("The meeting is at 3pm")
        assert result["predicted_sentiment"] == 0.0
