"""Tests for Multi-Agent Registry — creation, listing, deletion, isolation."""

import os
import shutil
import tempfile
import pytest

from humane.multi import AgentRegistry
from humane.core.models import EntityType, MemoryType, ProposedAction, Verdict


def _make_registry(base_path=None):
    if base_path is None:
        base_path = tempfile.mkdtemp(prefix="humane_test_multi_")
    return AgentRegistry(base_path=base_path), base_path


class TestAgentCreation:
    def test_create_agent_returns_id(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent("TestAgent")
            assert agent_id is not None
            assert isinstance(agent_id, str)
            assert len(agent_id) > 0
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_create_agent_sets_name(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent("MyAgent")
            agent = registry.get_agent(agent_id)
            assert agent["name"] == "MyAgent"
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_create_agent_has_conductor(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent("AgentWithConductor")
            conductor = registry.get_conductor(agent_id)
            assert conductor is not None
            snap = conductor.get_state_snapshot()
            assert "energy" in snap
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_create_agent_has_isolated_db(self):
        registry, base = _make_registry()
        try:
            id1 = registry.create_agent("Agent1")
            id2 = registry.create_agent("Agent2")
            agent1 = registry.get_agent(id1)
            agent2 = registry.get_agent(id2)
            assert agent1["db_path"] != agent2["db_path"]
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_create_duplicate_name_raises(self):
        registry, base = _make_registry()
        try:
            registry.create_agent("UniqueAgent")
            with pytest.raises(ValueError, match="already exists"):
                registry.create_agent("UniqueAgent")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_create_agent_with_config_overrides(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent(
                "CustomAgent",
                config_overrides={"impulse_base_rate_per_day": 10.0},
            )
            config = registry.get_config(agent_id)
            assert config.impulse_base_rate_per_day == 10.0
        finally:
            shutil.rmtree(base, ignore_errors=True)


class TestListAgents:
    def test_list_agents_empty(self):
        registry, base = _make_registry()
        try:
            agents = registry.list_agents()
            assert agents == []
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_list_agents_returns_all_created(self):
        registry, base = _make_registry()
        try:
            registry.create_agent("Agent1")
            registry.create_agent("Agent2")
            registry.create_agent("Agent3")
            agents = registry.list_agents()
            assert len(agents) == 3
            names = {a["name"] for a in agents}
            assert names == {"Agent1", "Agent2", "Agent3"}
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_list_agents_contains_expected_fields(self):
        registry, base = _make_registry()
        try:
            registry.create_agent("FieldTestAgent")
            agents = registry.list_agents()
            agent = agents[0]
            assert "id" in agent
            assert "name" in agent
            assert "status" in agent
            assert "created_at" in agent
            assert "db_path" in agent
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_list_agents_shows_running_status(self):
        registry, base = _make_registry()
        try:
            registry.create_agent("RunningAgent")
            agents = registry.list_agents()
            assert agents[0]["status"] == "running"
        finally:
            shutil.rmtree(base, ignore_errors=True)


class TestDeleteAgent:
    def test_delete_agent_removes_from_list(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent("ToDelete")
            registry.delete_agent(agent_id)
            agents = registry.list_agents()
            assert len(agents) == 0
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_delete_agent_removes_db_files(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent("ToDelete")
            agent_dir = registry.agents_dir / agent_id
            assert agent_dir.exists()
            registry.delete_agent(agent_id)
            assert not agent_dir.exists()
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_delete_nonexistent_agent_raises(self):
        registry, base = _make_registry()
        try:
            with pytest.raises(KeyError, match="not found"):
                registry.delete_agent("nonexistent-id")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_delete_only_removes_target(self):
        registry, base = _make_registry()
        try:
            id1 = registry.create_agent("Keep")
            id2 = registry.create_agent("Delete")
            registry.delete_agent(id2)
            agents = registry.list_agents()
            assert len(agents) == 1
            assert agents[0]["id"] == id1
        finally:
            shutil.rmtree(base, ignore_errors=True)


class TestAgentIsolation:
    def test_agents_have_independent_state(self):
        registry, base = _make_registry()
        try:
            id1 = registry.create_agent("Agent1")
            id2 = registry.create_agent("Agent2")

            cond1 = registry.get_conductor(id1)
            cond2 = registry.get_conductor(id2)

            # Modify state of agent 1
            cond1.human_state.energy = 0.1
            cond1.human_state.mood = -0.9
            cond1.human_state.save()

            # Agent 2 should be unaffected
            snap2 = cond2.get_state_snapshot()
            assert snap2["energy"] != 0.1
            assert snap2["mood"] != -0.9
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_agents_have_independent_entities(self):
        registry, base = _make_registry()
        try:
            id1 = registry.create_agent("Agent1")
            id2 = registry.create_agent("Agent2")

            cond1 = registry.get_conductor(id1)
            cond2 = registry.get_conductor(id2)

            # Add entity to agent 1
            cond1.relational.add_entity("Arjun", EntityType.PROSPECT)

            # Agent 2 should not have this entity
            entities2 = cond2.relational.list_entities()
            assert len(entities2) == 0

            entities1 = cond1.relational.list_entities()
            assert len(entities1) == 1
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_agents_have_independent_goals(self):
        registry, base = _make_registry()
        try:
            id1 = registry.create_agent("Agent1")
            id2 = registry.create_agent("Agent2")

            cond1 = registry.get_conductor(id1)
            cond2 = registry.get_conductor(id2)

            # Add goal to agent 1
            cond1.goal_engine.register_goal("Agent1 goal")

            # Agent 2 should not have this goal
            goals2 = cond2.goal_engine.active_goals()
            assert len(goals2) == 0

            goals1 = cond1.goal_engine.active_goals()
            assert len(goals1) == 1
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_agents_have_independent_evaluation(self):
        registry, base = _make_registry()
        try:
            id1 = registry.create_agent("Agent1")
            id2 = registry.create_agent("Agent2")

            cond1 = registry.get_conductor(id1)
            cond2 = registry.get_conductor(id2)

            # Set different states
            cond1.human_state.energy = 0.9
            cond1.human_state.fatigue = 0.1

            cond2.human_state.energy = 0.1
            cond2.human_state.fatigue = 0.9

            action = ProposedAction(
                action_type="test", payload={},
                confidence=0.8, rationale="test", source="user",
            )

            result1 = cond1.evaluate(action)
            result2 = cond2.evaluate(action)

            # Results should differ due to different states
            assert result1.final_verdict != result2.final_verdict or \
                   result1.gate_results != result2.gate_results
        finally:
            shutil.rmtree(base, ignore_errors=True)


class TestResolveAgentId:
    def test_resolve_returns_first_agent_when_none(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent("First")
            resolved = registry.resolve_agent_id(None)
            assert resolved == agent_id
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_resolve_raises_when_no_agents(self):
        registry, base = _make_registry()
        try:
            with pytest.raises(KeyError, match="No agents registered"):
                registry.resolve_agent_id(None)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_resolve_by_id(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent("ById")
            resolved = registry.resolve_agent_id(agent_id)
            assert resolved == agent_id
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_resolve_by_name(self):
        registry, base = _make_registry()
        try:
            agent_id = registry.create_agent("ByName")
            resolved = registry.resolve_agent_id("ByName")
            assert resolved == agent_id
        finally:
            shutil.rmtree(base, ignore_errors=True)
