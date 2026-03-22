"""Tests for Analytics endpoints — state-history, engine-stats, approval-rate, impulse-stats."""

import json
import os
import tempfile
import time
import pytest

from aiohttp.test_utils import TestClient, TestServer

from humane.conductor import Conductor
from humane.core.config import HumaneConfig
from humane.core.models import ProposedAction, ImpulseType
from humane.api.server import APIServer

_an_counter = 0


def _make_api():
    global _an_counter
    _an_counter += 1
    db_path = os.path.join(tempfile.gettempdir(), f"test_analytics_{os.getpid()}_{_an_counter}.db")
    config = HumaneConfig()
    config.db_path = db_path
    conductor = Conductor(config=config, db_path=db_path)
    api = APIServer(conductor, config)
    return api, conductor


class TestStateHistory:
    @pytest.fixture
    def api_and_conductor(self):
        return _make_api()

    @pytest.mark.asyncio
    async def test_state_history_returns_valid_structure(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/state-history")
            assert resp.status == 200
            data = await resp.json()
            assert "snapshots" in data
            assert "hours" in data
            assert isinstance(data["snapshots"], list)

    @pytest.mark.asyncio
    async def test_state_history_default_hours(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/state-history")
            data = await resp.json()
            assert data["hours"] == 24

    @pytest.mark.asyncio
    async def test_state_history_custom_hours(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/state-history?hours=48")
            data = await resp.json()
            assert data["hours"] == 48

    @pytest.mark.asyncio
    async def test_state_history_contains_state_dimensions(self, api_and_conductor):
        api, conductor = api_and_conductor

        # Log a human_state event so there is data
        conductor.event_log.log(
            event_type="state_tick",
            engine="human_state",
            data={
                "energy": 0.7,
                "mood": 0.3,
                "fatigue": 0.2,
                "boredom": 0.1,
                "social_load": 0.4,
                "focus": 0.6,
            },
        )

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/state-history")
            data = await resp.json()
            assert len(data["snapshots"]) >= 1
            snapshot = data["snapshots"][0]
            assert "timestamp" in snapshot
            assert "energy" in snapshot
            assert "mood" in snapshot
            assert "fatigue" in snapshot


class TestEngineStats:
    @pytest.fixture
    def api_and_conductor(self):
        return _make_api()

    @pytest.mark.asyncio
    async def test_engine_stats_returns_valid_structure(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/engine-stats")
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_engine_stats_aggregation_after_evaluation(self, api_and_conductor):
        api, conductor = api_and_conductor

        # Log gate_evaluation events for multiple engines
        conductor.event_log.log(
            event_type="gate_evaluation",
            engine="inaction_guard",
            data={"verdict": "proceed"},
        )
        conductor.event_log.log(
            event_type="gate_evaluation",
            engine="inaction_guard",
            data={"verdict": "hold"},
        )
        conductor.event_log.log(
            event_type="gate_evaluation",
            engine="values_boundary",
            data={"verdict": "proceed"},
        )

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/engine-stats")
            data = await resp.json()
            assert "inaction_guard" in data
            assert data["inaction_guard"]["proceed"] == 1
            assert data["inaction_guard"]["hold"] == 1
            assert data["inaction_guard"]["total"] == 2
            assert "values_boundary" in data
            assert data["values_boundary"]["proceed"] == 1

    @pytest.mark.asyncio
    async def test_engine_stats_empty_when_no_evaluations(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/engine-stats")
            data = await resp.json()
            assert data == {}


class TestApprovalRate:
    @pytest.fixture
    def api_and_conductor(self):
        return _make_api()

    @pytest.mark.asyncio
    async def test_approval_rate_returns_valid_structure(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/approval-rate")
            assert resp.status == 200
            data = await resp.json()
            assert "total" in data
            assert "approved" in data
            assert "rejected" in data
            assert "approval_rate" in data
            assert "by_engine" in data

    @pytest.mark.asyncio
    async def test_approval_rate_zero_when_no_holds(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/approval-rate")
            data = await resp.json()
            assert data["total"] == 0
            assert data["approval_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_approval_rate_calculation(self, api_and_conductor):
        api, conductor = api_and_conductor

        # Log 3 approved, 1 rejected
        for _ in range(3):
            conductor.event_log.log(
                event_type="hold_approved",
                engine="inaction_guard",
                data={},
            )
        conductor.event_log.log(
            event_type="hold_rejected",
            engine="inaction_guard",
            data={},
        )

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/approval-rate")
            data = await resp.json()
            assert data["total"] == 4
            assert data["approved"] == 3
            assert data["rejected"] == 1
            assert data["approval_rate"] == 0.75

    @pytest.mark.asyncio
    async def test_approval_rate_by_engine(self, api_and_conductor):
        api, conductor = api_and_conductor

        conductor.event_log.log(
            event_type="hold_approved",
            engine="inaction_guard",
            data={},
        )
        conductor.event_log.log(
            event_type="hold_rejected",
            engine="values_boundary",
            data={},
        )

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/approval-rate")
            data = await resp.json()
            assert "inaction_guard" in data["by_engine"]
            assert "values_boundary" in data["by_engine"]
            assert data["by_engine"]["inaction_guard"]["approved"] == 1
            assert data["by_engine"]["inaction_guard"]["rate"] == 1.0
            assert data["by_engine"]["values_boundary"]["rejected"] == 1
            assert data["by_engine"]["values_boundary"]["rate"] == 0.0


class TestImpulseStats:
    @pytest.fixture
    def api_and_conductor(self):
        return _make_api()

    @pytest.mark.asyncio
    async def test_impulse_stats_returns_valid_structure(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/impulse-stats")
            assert resp.status == 200
            data = await resp.json()
            assert "total" in data
            assert "by_type" in data
            assert "avg_per_day" in data

    @pytest.mark.asyncio
    async def test_impulse_stats_empty(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/impulse-stats")
            data = await resp.json()
            assert data["total"] == 0
            assert data["by_type"] == {}

    @pytest.mark.asyncio
    async def test_impulse_stats_counting(self, api_and_conductor):
        api, conductor = api_and_conductor

        # Log various impulse events
        conductor.event_log.log(
            event_type="idle_discovery",
            engine="impulse",
            data={"impulse_type": "idle_discovery"},
        )
        conductor.event_log.log(
            event_type="idle_discovery",
            engine="impulse",
            data={"impulse_type": "idle_discovery"},
        )
        conductor.event_log.log(
            event_type="proactive_reminder",
            engine="impulse",
            data={"impulse_type": "proactive_reminder"},
        )

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/impulse-stats")
            data = await resp.json()
            assert data["total"] == 3
            assert data["by_type"]["idle_discovery"] == 2
            assert data["by_type"]["proactive_reminder"] == 1

    @pytest.mark.asyncio
    async def test_impulse_stats_avg_per_day(self, api_and_conductor):
        api, conductor = api_and_conductor

        # Log impulse events (all at current time, so avg_per_day == total)
        conductor.event_log.log(
            event_type="idle_discovery",
            engine="impulse",
            data={},
        )
        conductor.event_log.log(
            event_type="proactive_reminder",
            engine="impulse",
            data={},
        )

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/analytics/impulse-stats")
            data = await resp.json()
            assert data["total"] == 2
            # With all events at the same time, avg_per_day should equal total
            assert data["avg_per_day"] == 2.0
