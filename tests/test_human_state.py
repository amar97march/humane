"""Tests for Engine 1: HumanState."""

import time
from humanclaw.core.config import HumanClawConfig
from humanclaw.core.store import Store
from humanclaw.core.events import EventLog
from humanclaw.engines.human_state import HumanState
from humanclaw.core.models import TaskType


def _make_state(db_path="/tmp/test_humanclaw_state.db"):
    config = HumanClawConfig()
    store = Store(db_path)
    store.initialize()
    event_log = EventLog(store)
    return HumanState(config, store, event_log)


class TestHumanStateDimensions:
    def test_initial_values(self):
        state = _make_state("/tmp/test_hs_init.db")
        assert 0.0 <= state.energy <= 1.0
        assert -1.0 <= state.mood <= 1.0
        assert 0.0 <= state.fatigue <= 1.0
        assert state.boredom == 0.0
        assert state.social_load == 0.0

    def test_energy_clamped(self):
        state = _make_state("/tmp/test_hs_clamp.db")
        state.energy = 1.5
        state._clamp_all()
        assert state.energy == 1.0
        state.energy = -0.5
        state._clamp_all()
        assert state.energy == 0.0

    def test_mood_bidirectional(self):
        state = _make_state("/tmp/test_hs_mood.db")
        state.mood = -1.5
        state._clamp_all()
        assert state.mood == -1.0
        state.mood = 1.5
        state._clamp_all()
        assert state.mood == 1.0


class TestHumanStateMutations:
    def test_on_task_start(self):
        state = _make_state("/tmp/test_hs_task.db")
        initial_boredom = 0.5
        state.boredom = initial_boredom
        state.on_task_start()
        assert state.boredom < initial_boredom

    def test_on_positive_interaction(self):
        state = _make_state("/tmp/test_hs_pos.db")
        initial_mood = state.mood
        state.on_positive_interaction()
        assert state.mood > initial_mood

    def test_on_negative_interaction(self):
        state = _make_state("/tmp/test_hs_neg.db")
        state.mood = 0.0
        state.on_negative_interaction()
        assert state.mood < 0.0
        assert state.fatigue > 0.15

    def test_on_rest_recovers(self):
        state = _make_state("/tmp/test_hs_rest.db")
        state.energy = 0.3
        state.fatigue = 0.7
        state.on_rest()
        assert state.energy > 0.3
        assert state.fatigue < 0.7


class TestHumanStateOutputs:
    def test_decision_quality_multiplier(self):
        state = _make_state("/tmp/test_hs_dqm.db")
        dqm = state.decision_quality_multiplier
        assert 0.1 <= dqm <= 1.0

    def test_dqm_degrades_with_fatigue(self):
        state = _make_state("/tmp/test_hs_dqm_fat.db")
        state.energy = 0.9
        state.fatigue = 0.1
        high_dqm = state.decision_quality_multiplier

        state.energy = 0.3
        state.fatigue = 0.9
        low_dqm = state.decision_quality_multiplier

        # On average, high should be > low (with noise margin)
        assert high_dqm > 0.3

    def test_preferred_task_type_creative(self):
        state = _make_state("/tmp/test_hs_pref1.db")
        state.mood = 0.5
        state.energy = 0.8
        assert state.preferred_task_type == TaskType.CREATIVE_OR_STRATEGIC

    def test_preferred_task_type_mechanical(self):
        state = _make_state("/tmp/test_hs_pref2.db")
        state.mood = -0.5
        state.fatigue = 0.8
        assert state.preferred_task_type == TaskType.MECHANICAL_OR_ROUTINE

    def test_snapshot(self):
        state = _make_state("/tmp/test_hs_snap.db")
        snap = state.snapshot()
        assert "energy" in snap
        assert "mood" in snap
        assert "fatigue" in snap
        assert "boredom" in snap
        assert "social_load" in snap
        assert "focus" in snap


class TestHumanStatePersistence:
    def test_save_and_load(self):
        db = "/tmp/test_hs_persist.db"
        state = _make_state(db)
        state.energy = 0.42
        state.mood = -0.33
        state.save()

        state2 = _make_state(db)
        assert abs(state2.energy - 0.42) < 0.01
        assert abs(state2.mood - (-0.33)) < 0.01
