"""Tests for the Conductor — full gate stack integration."""

from humanclaw.conductor import Conductor
from humanclaw.core.models import ProposedAction, Verdict


def _make_conductor(db_path="/tmp/test_conductor.db"):
    from humanclaw.core.config import HumanClawConfig
    config = HumanClawConfig()
    config.db_path = db_path
    return Conductor(config=config, db_path=db_path)


class TestConductorGateStack:
    def test_high_confidence_proceeds(self):
        conductor = _make_conductor("/tmp/test_cond_proceed.db")
        conductor.human_state.energy = 0.9
        conductor.human_state.fatigue = 0.1
        action = ProposedAction(
            action_type="test_action", payload={"msg": "hello"},
            confidence=0.95, rationale="test", source="user",
        )
        result = conductor.evaluate(action)
        assert result.final_verdict == Verdict.PROCEED
        assert len(result.gate_results) >= 3
        assert len(result.audit_trail) > 0

    def test_low_confidence_holds(self):
        conductor = _make_conductor("/tmp/test_cond_hold.db")
        action = ProposedAction(
            action_type="test_action", payload={},
            confidence=0.3, rationale="test", source="user",
        )
        result = conductor.evaluate(action)
        assert result.final_verdict == Verdict.HOLD
        assert result.hold_item is not None

    def test_audit_trail_populated(self):
        conductor = _make_conductor("/tmp/test_cond_audit.db")
        action = ProposedAction(
            action_type="test_action", payload={},
            confidence=0.8, rationale="test", source="user",
        )
        result = conductor.evaluate(action)
        assert len(result.audit_trail) >= 3
        assert any("State tick" in a for a in result.audit_trail)

    def test_gate_results_contain_all_engines(self):
        conductor = _make_conductor("/tmp/test_cond_gates.db")
        conductor.human_state.energy = 0.9
        conductor.human_state.fatigue = 0.1
        action = ProposedAction(
            action_type="test_action", payload={},
            confidence=0.95, rationale="test", source="user",
        )
        result = conductor.evaluate(action)
        engines = {gr.engine for gr in result.gate_results}
        assert "values_boundary" in engines
        assert "social_risk" in engines
        assert "dissent" in engines
        assert "inaction_guard" in engines

    def test_hold_queue_management(self):
        conductor = _make_conductor("/tmp/test_cond_queue.db")
        action = ProposedAction(
            action_type="test", payload={}, confidence=0.2,
            rationale="test", source="user",
        )
        result = conductor.evaluate(action)
        assert result.hold_item is not None

        queue = conductor.get_hold_queue()
        assert len(queue) >= 1

        conductor.approve_hold(result.hold_item.id)


class TestConductorTick:
    def test_tick_does_not_crash(self):
        conductor = _make_conductor("/tmp/test_cond_tick.db")
        result = conductor.tick()
        # May return None if no impulse fires (expected)


class TestConductorStateSnapshot:
    def test_snapshot_returns_all_dims(self):
        conductor = _make_conductor("/tmp/test_cond_snap.db")
        snap = conductor.get_state_snapshot()
        assert "energy" in snap
        assert "mood" in snap
        assert "fatigue" in snap
        assert "boredom" in snap
        assert "social_load" in snap
        assert "focus" in snap
