"""Tests for Conversation History endpoints — list, stats, search, delete."""

import json
import os
import tempfile
import time
import pytest

from aiohttp.test_utils import TestClient, TestServer

from humane.conductor import Conductor
from humane.core.config import HumaneConfig
from humane.api.server import APIServer

_conv_counter = 0


def _make_api():
    global _conv_counter
    _conv_counter += 1
    db_path = os.path.join(tempfile.gettempdir(), f"test_conv_{os.getpid()}_{_conv_counter}.db")
    config = HumaneConfig()
    config.db_path = db_path
    conductor = Conductor(config=config, db_path=db_path)
    api = APIServer(conductor, config)
    return api, conductor


def _insert_conversation(conductor, chat_id, user_id, role, content, sentiment=0.0, created_at=None):
    """Insert a conversation record directly into the store."""
    import uuid
    conn = conductor.store.conn
    if created_at is None:
        created_at = time.time()
    with conn:
        conn.execute(
            """INSERT INTO conversations (id, chat_id, user_id, role, content, sentiment, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), chat_id, user_id, role, content, sentiment, created_at),
        )


class TestListConversations:
    @pytest.fixture
    def api_and_conductor(self):
        return _make_api()

    @pytest.mark.asyncio
    async def test_get_conversations_returns_messages(self, api_and_conductor):
        api, conductor = api_and_conductor

        _insert_conversation(conductor, 100, 1, "user", "Hello there")
        _insert_conversation(conductor, 100, 0, "assistant", "Hi! How can I help?")

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations")
            assert resp.status == 200
            data = await resp.json()
            assert "conversations" in data
            assert len(data["conversations"]) == 2
            assert "total" in data

    @pytest.mark.asyncio
    async def test_get_conversations_empty(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations")
            assert resp.status == 200
            data = await resp.json()
            assert data["conversations"] == []
            assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_conversations_with_limit(self, api_and_conductor):
        api, conductor = api_and_conductor

        for i in range(10):
            _insert_conversation(conductor, 100, 1, "user", f"Message {i}")

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations?limit=3")
            data = await resp.json()
            assert len(data["conversations"]) == 3
            assert data["total"] == 10

    @pytest.mark.asyncio
    async def test_get_conversations_with_offset(self, api_and_conductor):
        api, conductor = api_and_conductor

        for i in range(5):
            _insert_conversation(conductor, 100, 1, "user", f"Message {i}")

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations?limit=2&offset=3")
            data = await resp.json()
            assert len(data["conversations"]) == 2

    @pytest.mark.asyncio
    async def test_get_conversations_contains_expected_fields(self, api_and_conductor):
        api, conductor = api_and_conductor

        _insert_conversation(conductor, 100, 1, "user", "Test message", sentiment=0.5)

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations")
            data = await resp.json()
            msg = data["conversations"][0]
            assert "id" in msg
            assert "chat_id" in msg
            assert "user_id" in msg
            assert "role" in msg
            assert "content" in msg
            assert "sentiment" in msg
            assert "created_at" in msg


class TestConversationFiltering:
    @pytest.fixture
    def api_and_conductor(self):
        return _make_api()

    @pytest.mark.asyncio
    async def test_filter_by_chat_id(self, api_and_conductor):
        api, conductor = api_and_conductor

        _insert_conversation(conductor, 100, 1, "user", "Chat 100 message")
        _insert_conversation(conductor, 200, 2, "user", "Chat 200 message")
        _insert_conversation(conductor, 100, 1, "assistant", "Reply in chat 100")

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations?chat_id=100")
            data = await resp.json()
            assert len(data["conversations"]) == 2
            assert all(c["chat_id"] == 100 for c in data["conversations"])

    @pytest.mark.asyncio
    async def test_filter_by_chat_id_no_results(self, api_and_conductor):
        api, conductor = api_and_conductor

        _insert_conversation(conductor, 100, 1, "user", "Only chat 100")

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations?chat_id=999")
            data = await resp.json()
            assert len(data["conversations"]) == 0
            assert data["total"] == 0


class TestConversationStats:
    @pytest.fixture
    def api_and_conductor(self):
        return _make_api()

    @pytest.mark.asyncio
    async def test_stats_returns_valid_structure(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations/stats")
            assert resp.status == 200
            data = await resp.json()
            assert "total_count" in data
            assert "avg_sentiment" in data
            assert "avg_messages_per_day" in data
            assert "messages_by_role" in data
            assert "daily_counts" in data

    @pytest.mark.asyncio
    async def test_stats_empty_database(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations/stats")
            data = await resp.json()
            assert data["total_count"] == 0
            assert data["avg_sentiment"] == 0.0

    @pytest.mark.asyncio
    async def test_stats_total_count(self, api_and_conductor):
        api, conductor = api_and_conductor

        _insert_conversation(conductor, 100, 1, "user", "Msg 1", sentiment=0.5)
        _insert_conversation(conductor, 100, 0, "assistant", "Reply 1", sentiment=0.3)
        _insert_conversation(conductor, 100, 1, "user", "Msg 2", sentiment=-0.2)

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations/stats")
            data = await resp.json()
            assert data["total_count"] == 3

    @pytest.mark.asyncio
    async def test_stats_avg_sentiment(self, api_and_conductor):
        api, conductor = api_and_conductor

        _insert_conversation(conductor, 100, 1, "user", "Good", sentiment=0.8)
        _insert_conversation(conductor, 100, 1, "user", "Bad", sentiment=-0.4)

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations/stats")
            data = await resp.json()
            # Average of 0.8 and -0.4 = 0.2
            assert abs(data["avg_sentiment"] - 0.2) < 0.01

    @pytest.mark.asyncio
    async def test_stats_messages_by_role(self, api_and_conductor):
        api, conductor = api_and_conductor

        _insert_conversation(conductor, 100, 1, "user", "Msg 1")
        _insert_conversation(conductor, 100, 1, "user", "Msg 2")
        _insert_conversation(conductor, 100, 0, "assistant", "Reply 1")

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.get("/api/conversations/stats")
            data = await resp.json()
            assert data["messages_by_role"].get("user") == 2
            assert data["messages_by_role"].get("assistant") == 1


class TestDeleteConversations:
    @pytest.fixture
    def api_and_conductor(self):
        return _make_api()

    @pytest.mark.asyncio
    async def test_delete_all_conversations(self, api_and_conductor):
        api, conductor = api_and_conductor

        _insert_conversation(conductor, 100, 1, "user", "Msg 1")
        _insert_conversation(conductor, 100, 0, "assistant", "Reply 1")

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.delete("/api/conversations")
            assert resp.status == 200
            data = await resp.json()
            assert data["ok"] is True
            assert data["deleted"] == 2

            # Verify empty
            resp = await client.get("/api/conversations")
            data = await resp.json()
            assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_delete_with_timestamp_filter(self, api_and_conductor):
        api, conductor = api_and_conductor

        old_time = time.time() - 86400  # 1 day ago
        new_time = time.time()

        _insert_conversation(conductor, 100, 1, "user", "Old message", created_at=old_time)
        _insert_conversation(conductor, 100, 1, "user", "New message", created_at=new_time)

        # Delete messages older than current time (should only delete old message)
        cutoff = time.time() - 3600  # 1 hour ago
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.delete(f"/api/conversations?before={cutoff}")
            data = await resp.json()
            assert data["ok"] is True
            assert data["deleted"] == 1

            # Verify new message still exists
            resp = await client.get("/api/conversations")
            data = await resp.json()
            assert data["total"] == 1
            assert data["conversations"][0]["content"] == "New message"

    @pytest.mark.asyncio
    async def test_delete_empty_database(self, api_and_conductor):
        api, conductor = api_and_conductor
        async with TestClient(TestServer(api.app)) as client:
            resp = await client.delete("/api/conversations")
            data = await resp.json()
            assert data["ok"] is True
            assert data["deleted"] == 0

    @pytest.mark.asyncio
    async def test_delete_returns_correct_count(self, api_and_conductor):
        api, conductor = api_and_conductor

        for i in range(5):
            _insert_conversation(conductor, 100, 1, "user", f"Msg {i}")

        async with TestClient(TestServer(api.app)) as client:
            resp = await client.delete("/api/conversations")
            data = await resp.json()
            assert data["deleted"] == 5
