"""Tests for the Brain — decision engine for the bot."""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from humane.conductor import Conductor
from humane.core.config import HumaneConfig
from humane.core.models import EntityType, MemoryType


@pytest.fixture
def conductor():
    config = HumaneConfig()
    config.db_path = "/tmp/test_brain.db"
    return Conductor(config=config, db_path=config.db_path)


@pytest.fixture
def conversation_mock():
    mock = MagicMock()
    mock.generate_response = AsyncMock(return_value="Sure, I'll look into that.")
    mock.analyze_sentiment = AsyncMock(return_value=0.3)
    mock.generate_impulse_message = AsyncMock(return_value="Hey, just thinking about that proposal...")
    mock.generate_reminder = AsyncMock(return_value="Did you get to that thing?")
    return mock


@pytest.fixture
def brain(conductor, conversation_mock):
    from humane.bot.brain import Brain
    return Brain(conductor, conversation_mock)


class TestEntityManagement:
    def test_ensure_entity_creates_new(self, brain):
        entity_id = brain._ensure_entity(12345, "TestUser")
        assert entity_id is not None
        assert 12345 in brain._chat_entity_map

    def test_ensure_entity_reuses_existing(self, brain):
        id1 = brain._ensure_entity(12345, "TestUser")
        id2 = brain._ensure_entity(12345, "TestUser")
        assert id1 == id2


class TestConversationHistory:
    def test_add_to_history(self, brain):
        brain._add_to_history(123, "user", "hello")
        brain._add_to_history(123, "assistant", "hi there")
        history = brain._get_history(123)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_history_limit(self, brain):
        for i in range(60):
            brain._add_to_history(123, "user", f"message {i}")
        assert len(brain._get_history(123)) == 50


class TestDeferralDetection:
    def test_detects_not_now(self, brain):
        # Register a reminder first
        brain._ensure_entity(123, "Test")
        brain.register_reminder(123, "Call Arjun")
        result = brain._check_deferral(123, "not now")
        assert result is not None
        assert "later" in result.lower() or "circle back" in result.lower() or "worries" in result.lower()

    def test_no_deferral_on_normal_text(self, brain):
        result = brain._check_deferral(123, "what's the weather like?")
        assert result is None


class TestContextSearch:
    def test_finds_related_memories(self, brain):
        brain.conductor.memory_decay.add_memory(MemoryType.EPISODIC, "Meeting with Arjun about proposal")
        result = brain.find_related_context("How is the Arjun proposal going?")
        assert len(result["memories"]) > 0

    def test_finds_related_goals(self, brain):
        brain.conductor.goal_engine.register_goal("Close design studio deal")
        result = brain.find_related_context("What about the design studio?")
        assert len(result["links"]) > 0


class TestReminderRegistration:
    def test_register_reminder(self, brain):
        brain._ensure_entity(123, "Test")
        reminder_id = brain.register_reminder(123, "Call Arjun tomorrow")
        assert reminder_id is not None


@pytest.mark.asyncio
class TestMessageProcessing:
    async def test_on_user_message_returns_response(self, brain):
        response = await brain.on_user_message(123, 456, "TestUser", "Hello!")
        assert response is not None
        assert isinstance(response, str)

    async def test_on_user_message_updates_state(self, brain):
        initial_social = brain.conductor.human_state.social_load
        await brain.on_user_message(123, 456, "TestUser", "Great news!")
        assert brain.conductor.human_state.social_load >= initial_social
