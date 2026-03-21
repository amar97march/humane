"""Tests for Engine 2: Stochastic Impulse."""

from humane.core.config import HumaneConfig
from humane.core.store import Store
from humane.core.events import EventLog
from humane.core.models import ImpulseType
from humane.engines.human_state import HumanState
from humane.engines.impulse import StochasticImpulseEngine


def _make_impulse(db_path="/tmp/test_impulse.db"):
    config = HumaneConfig()
    store = Store(db_path)
    store.initialize()
    event_log = EventLog(store)
    human_state = HumanState(config, store, event_log)
    engine = StochasticImpulseEngine(config, human_state, event_log)
    return engine, human_state


class TestImpulseEngine:
    def test_effective_rate_increases_with_boredom(self):
        engine, state = _make_impulse("/tmp/test_imp_rate.db")
        state.boredom = 0.0
        low_rate = engine._effective_rate()
        state.boredom = 0.9
        high_rate = engine._effective_rate()
        assert high_rate > low_rate

    def test_select_type_returns_valid(self):
        engine, _ = _make_impulse("/tmp/test_imp_type.db")
        for _ in range(20):
            t = engine._select_type()
            assert isinstance(t, ImpulseType)

    def test_force_fire_returns_event(self):
        engine, _ = _make_impulse("/tmp/test_imp_force.db")
        event = engine.force_fire(ImpulseType.IDLE_DISCOVERY)
        assert event.impulse_type == ImpulseType.IDLE_DISCOVERY
        assert event.id is not None

    def test_schedule_next_produces_future_time(self):
        engine, _ = _make_impulse("/tmp/test_imp_sched.db")
        import time
        next_time = engine._schedule_next()
        assert next_time > time.time()
