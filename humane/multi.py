"""Humane Multi-Agent Registry — run multiple independent agents from one server."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

try:
    import yaml
except ImportError:
    yaml = None

from humane.conductor import Conductor
from humane.core.config import HumaneConfig, load_config, save_config


class AgentRegistry:
    """Manages multiple independent Humane agents, each with its own DB and Conductor."""

    def __init__(self, base_path: str = "~/.humane"):
        self.base_path = Path(os.path.expanduser(base_path))
        self.agents_dir = self.base_path / "agents"
        self.registry_file = self.base_path / "registry.json"

        # Ensure directories exist
        self.agents_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache of active conductors
        self._conductors: dict[str, Conductor] = {}
        self._configs: dict[str, HumaneConfig] = {}

        # Load or create registry
        self._registry = self._load_registry()

        # Boot existing agents
        self._boot_all()

    def _load_registry(self) -> dict:
        if self.registry_file.exists():
            with open(self.registry_file, "r") as f:
                return json.load(f)
        return {"agents": []}

    def _save_registry(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, "w") as f:
            json.dump(self._registry, f, indent=2, default=str)

    def _boot_all(self) -> None:
        """Boot Conductor instances for all registered agents."""
        for entry in self._registry["agents"]:
            agent_id = entry["id"]
            if agent_id not in self._conductors:
                try:
                    self._boot_agent(agent_id)
                except Exception:
                    # Agent may have corrupt config; skip but keep in registry
                    pass

    def _boot_agent(self, agent_id: str) -> None:
        """Create a Conductor instance for an agent."""
        agent_dir = self.agents_dir / agent_id
        config_path = agent_dir / "config.yaml"
        db_path = str(agent_dir / "agent.db")

        if config_path.exists() and yaml is not None:
            config = load_config(str(config_path))
        else:
            config = HumaneConfig()

        config.db_path = db_path
        conductor = Conductor(config=config, db_path=db_path)
        self._conductors[agent_id] = conductor
        self._configs[agent_id] = config

    def create_agent(self, name: str, config_overrides: dict[str, Any] | None = None) -> str:
        """Create a new agent with its own DB, config, and Conductor.

        Returns the agent_id.
        """
        if config_overrides is None:
            config_overrides = {}

        # Check for duplicate names
        for entry in self._registry["agents"]:
            if entry["name"] == name:
                raise ValueError(f"Agent with name '{name}' already exists (id={entry['id']})")

        agent_id = str(uuid4())[:8]
        agent_dir = self.agents_dir / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Build config
        config = HumaneConfig()
        config.agent_name = name
        config.db_path = str(agent_dir / "agent.db")

        # Apply overrides
        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        # Save config YAML
        if yaml is not None:
            save_config(config, str(agent_dir / "config.yaml"))

        # Register
        entry = {
            "id": agent_id,
            "name": name,
            "created_at": time.time(),
        }
        self._registry["agents"].append(entry)
        self._save_registry()

        # Boot
        self._boot_agent(agent_id)

        return agent_id

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """Return conductor, config, and metadata for an agent.

        Raises KeyError if agent_id is not found.
        """
        entry = self._find_entry(agent_id)
        if entry is None:
            raise KeyError(f"Agent '{agent_id}' not found")

        if agent_id not in self._conductors:
            self._boot_agent(agent_id)

        return {
            "conductor": self._conductors[agent_id],
            "config": self._configs[agent_id],
            "id": entry["id"],
            "name": entry["name"],
            "created_at": entry["created_at"],
            "db_path": str(self.agents_dir / agent_id / "agent.db"),
        }

    def get_conductor(self, agent_id: str) -> Conductor:
        """Shortcut to get just the Conductor for an agent."""
        return self.get_agent(agent_id)["conductor"]

    def get_config(self, agent_id: str) -> HumaneConfig:
        """Shortcut to get just the config for an agent."""
        return self.get_agent(agent_id)["config"]

    def list_agents(self) -> list[dict[str, Any]]:
        """Return list of all registered agents with metadata."""
        result = []
        for entry in self._registry["agents"]:
            agent_id = entry["id"]
            status = "running" if agent_id in self._conductors else "stopped"
            result.append({
                "id": agent_id,
                "name": entry["name"],
                "status": status,
                "created_at": entry["created_at"],
                "db_path": str(self.agents_dir / agent_id / "agent.db"),
            })
        return result

    def delete_agent(self, agent_id: str) -> None:
        """Remove an agent and its data (DB, config)."""
        entry = self._find_entry(agent_id)
        if entry is None:
            raise KeyError(f"Agent '{agent_id}' not found")

        # Tear down conductor
        if agent_id in self._conductors:
            del self._conductors[agent_id]
        if agent_id in self._configs:
            del self._configs[agent_id]

        # Remove from registry
        self._registry["agents"] = [
            e for e in self._registry["agents"] if e["id"] != agent_id
        ]
        self._save_registry()

        # Remove files
        agent_dir = self.agents_dir / agent_id
        if agent_dir.exists():
            import shutil
            shutil.rmtree(agent_dir)

    def resolve_agent_id(self, agent_id: Optional[str] = None) -> str:
        """Resolve an agent_id, returning the primary (first) agent if None.

        Raises KeyError if no agents exist and agent_id is None.
        """
        if agent_id is not None:
            # Also support lookup by name
            entry = self._find_entry(agent_id)
            if entry is None:
                entry = self._find_entry_by_name(agent_id)
            if entry is None:
                raise KeyError(f"Agent '{agent_id}' not found")
            return entry["id"]

        if not self._registry["agents"]:
            raise KeyError("No agents registered")
        return self._registry["agents"][0]["id"]

    def _find_entry(self, agent_id: str) -> Optional[dict]:
        for entry in self._registry["agents"]:
            if entry["id"] == agent_id:
                return entry
        return None

    def _find_entry_by_name(self, name: str) -> Optional[dict]:
        for entry in self._registry["agents"]:
            if entry["name"] == name:
                return entry
        return None
