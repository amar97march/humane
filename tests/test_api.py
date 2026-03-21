"""Tests for the REST API server."""

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from humane.conductor import Conductor
from humane.core.config import HumaneConfig
from humane.api.server import APIServer


def _make_api(db_path="/tmp/test_api.db"):
    config = HumaneConfig()
    config.db_path = db_path
    conductor = Conductor(config=config, db_path=db_path)
    api = APIServer(conductor, config)
    return api


class TestAPIState:
    @pytest.fixture
    def api(self):
        return _make_api("/tmp/test_api_state.db")

    @pytest.mark.asyncio
    async def test_get_state(self, api):
        from aiohttp.test_utils import TestClient, TestServer
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/state")
            assert resp.status == 200
            data = await resp.json()
            assert "state" in data
            assert "energy" in data["state"]
            assert "dqm" in data


class TestAPIQueue:
    @pytest.fixture
    def api(self):
        return _make_api("/tmp/test_api_queue.db")

    @pytest.mark.asyncio
    async def test_get_empty_queue(self, api):
        from aiohttp.test_utils import TestClient, TestServer
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/queue")
            assert resp.status == 200
            data = await resp.json()
            assert data["count"] == 0


class TestAPIEntities:
    @pytest.fixture
    def api(self):
        return _make_api("/tmp/test_api_entities.db")

    @pytest.mark.asyncio
    async def test_add_and_list_entities(self, api):
        from aiohttp.test_utils import TestClient, TestServer
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.post("/api/entities", json={"name": "Arjun", "entity_type": "prospect"})
            assert resp.status == 201
            data = await resp.json()
            entity_id = data["entity_id"]

            resp = await client.get("/api/entities")
            assert resp.status == 200
            data = await resp.json()
            assert len(data["entities"]) >= 1


class TestAPIEvaluate:
    @pytest.fixture
    def api(self):
        return _make_api("/tmp/test_api_eval.db")

    @pytest.mark.asyncio
    async def test_evaluate_action(self, api):
        from aiohttp.test_utils import TestClient, TestServer
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.post("/api/evaluate", json={
                "action_type": "send_message",
                "payload": {"msg": "hello"},
                "confidence": 0.9,
                "rationale": "test",
            })
            assert resp.status == 200
            data = await resp.json()
            assert "verdict" in data
            assert "gate_results" in data
            assert len(data["gate_results"]) >= 3


class TestAPIGoals:
    @pytest.fixture
    def api(self):
        return _make_api("/tmp/test_api_goals.db")

    @pytest.mark.asyncio
    async def test_add_goal(self, api):
        from aiohttp.test_utils import TestClient, TestServer
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.post("/api/goals", json={
                "description": "Close deal",
                "expected_value": 0.8,
            })
            assert resp.status == 201


class TestAPIValues:
    @pytest.fixture
    def api(self):
        return _make_api("/tmp/test_api_values.db")

    @pytest.mark.asyncio
    async def test_add_value(self, api):
        from aiohttp.test_utils import TestClient, TestServer
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.post("/api/values", json={
                "description": "Never lie",
                "behavioral_pattern": "Honesty",
                "severity": "hard",
            })
            assert resp.status == 201
