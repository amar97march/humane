"""Tests for Engine 3: InactionGuard."""

from humane.core.config import HumaneConfig
from humane.core.store import Store
from humane.core.events import EventLog
from humane.core.models import ProposedAction, Verdict
from humane.engines.human_state import HumanState
from humane.engines.inaction_guard import InactionGuard


def _make_guard(db_path="/tmp/test_ig.db"):
    config = HumaneConfig()
    store = Store(db_path)
    store.initialize()
    event_log = EventLog(store)
    human_state = HumanState(config, store, event_log)
    guard = InactionGuard(config, human_state, store, event_log)
    return guard, human_state, store


class TestInactionGuardVerdicts:
    def test_high_confidence_proceeds(self):
        guard, state, _ = _make_guard("/tmp/test_ig_proceed.db")
        state.energy = 0.9
        state.fatigue = 0.1
        action = ProposedAction(
            action_type="test", payload={}, confidence=0.95,
            rationale="test", source="user",
        )
        result = guard.evaluate(action)
        assert result.verdict == Verdict.PROCEED

    def test_low_confidence_holds(self):
        guard, state, _ = _make_guard("/tmp/test_ig_hold.db")
        action = ProposedAction(
            action_type="test", payload={}, confidence=0.3,
            rationale="test", source="user",
        )
        result = guard.evaluate(action)
        assert result.verdict == Verdict.HOLD

    def test_high_fatigue_defers(self):
        guard, state, _ = _make_guard("/tmp/test_ig_defer.db")
        state.fatigue = 0.95
        action = ProposedAction(
            action_type="test", payload={}, confidence=0.9,
            rationale="test", source="user",
        )
        result = guard.evaluate(action)
        assert result.verdict == Verdict.DEFER

    def test_confidence_adjusted_by_dqm(self):
        guard, state, _ = _make_guard("/tmp/test_ig_dqm.db")
        state.energy = 0.5
        state.fatigue = 0.5
        action = ProposedAction(
            action_type="test", payload={}, confidence=0.7,
            rationale="test", source="user",
        )
        result = guard.evaluate(action)
        assert result.score < 0.7  # DQM should reduce confidence


class TestHoldQueue:
    def test_hold_item_created(self):
        guard, state, store = _make_guard("/tmp/test_ig_queue.db")
        action = ProposedAction(
            action_type="test", payload={}, confidence=0.3,
            rationale="test", source="user",
        )
        result = guard.evaluate(action)
        assert result.verdict == Verdict.HOLD

        hold = guard.create_hold_item(action, result, "inaction_guard")
        assert hold.id is not None
        assert hold.hold_source == "inaction_guard"

    def test_approve_hold(self):
        guard, state, store = _make_guard("/tmp/test_ig_approve.db")
        action = ProposedAction(
            action_type="test", payload={}, confidence=0.3,
            rationale="test", source="user",
        )
        result = guard.evaluate(action)
        hold = guard.create_hold_item(action, result, "inaction_guard")
        guard.approve(hold.id)
        queue = store.get_hold_queue()
        assert len(queue) == 0  # resolved items excluded by default
