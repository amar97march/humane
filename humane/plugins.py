"""Humane Plugin System — extensible gate engine via drop-in .py files."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from humane.core.models import GateResult, ProposedAction

logger = logging.getLogger("humane.plugins")


class HumanePlugin(ABC):
    """Abstract base class for Humane plugins.

    Subclass this to create a custom gate engine that participates
    in the Conductor's decision stack.
    """

    name: str = "unnamed_plugin"
    version: str = "0.0.1"

    @abstractmethod
    def evaluate(self, action: ProposedAction, context: dict) -> GateResult:
        """Evaluate a proposed action and return a gate result.

        Args:
            action: The action being evaluated.
            context: Dictionary with current state info (energy, mood, fatigue, etc.).

        Returns:
            GateResult with verdict, score, and reason.
        """
        ...

    def on_load(self, conductor) -> None:
        """Called when the plugin is loaded into the Conductor.

        Override to perform initialization that requires access to the conductor.
        """
        pass

    def on_unload(self) -> None:
        """Called when the plugin is unloaded.

        Override to clean up resources.
        """
        pass


class PluginManager:
    """Discovers, loads, and manages HumanePlugin instances."""

    def __init__(self, plugins_dir: str = "~/.humane/plugins"):
        self.plugins_dir = Path(plugins_dir).expanduser()
        self._plugins: Dict[str, HumanePlugin] = {}
        self._plugin_files: Dict[str, str] = {}  # name -> file_path
        self._disabled: set[str] = set()
        self._conductor = None

    def set_conductor(self, conductor) -> None:
        """Store a reference to the conductor for plugin on_load calls."""
        self._conductor = conductor

    def discover(self) -> List[Dict[str, Any]]:
        """Scan plugins_dir for .py files and find HumanePlugin subclasses.

        Returns a list of dicts with info about discovered plugin classes,
        without loading them.
        """
        discovered = []

        if not self.plugins_dir.exists():
            logger.debug("Plugins directory does not exist: %s", self.plugins_dir)
            return discovered

        for py_file in sorted(self.plugins_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                classes = self._find_plugin_classes(py_file)
                for cls in classes:
                    discovered.append({
                        "class": cls,
                        "name": getattr(cls, "name", cls.__name__),
                        "version": getattr(cls, "version", "0.0.1"),
                        "file_path": str(py_file),
                    })
            except Exception as e:
                logger.warning("Failed to scan %s: %s", py_file, e)

        return discovered

    def _find_plugin_classes(self, py_file: Path) -> List[type]:
        """Import a .py file and return all HumanePlugin subclasses found in it."""
        module_name = f"humane_plugin_{py_file.stem}"

        spec = importlib.util.spec_from_file_location(module_name, str(py_file))
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        classes = []
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, HumanePlugin)
                and obj is not HumanePlugin
                and obj.__module__ == module_name
            ):
                classes.append(obj)

        return classes

    def load(self, plugin_class: type) -> None:
        """Instantiate and register a plugin class.

        Args:
            plugin_class: A subclass of HumanePlugin to instantiate.
        """
        if not issubclass(plugin_class, HumanePlugin):
            raise TypeError(f"{plugin_class} is not a HumanePlugin subclass")

        instance = plugin_class()
        name = instance.name

        if name in self._plugins:
            logger.warning("Plugin '%s' is already loaded — replacing", name)
            self._plugins[name].on_unload()

        self._plugins[name] = instance

        if self._conductor is not None:
            instance.on_load(self._conductor)

        logger.info("Loaded plugin: %s v%s", name, instance.version)

    def unload(self, plugin_name: str) -> None:
        """Remove a plugin from the gate stack by name.

        Args:
            plugin_name: The name of the plugin to remove.
        """
        plugin = self._plugins.pop(plugin_name, None)
        if plugin is None:
            raise KeyError(f"Plugin '{plugin_name}' is not loaded")

        plugin.on_unload()
        self._plugin_files.pop(plugin_name, None)
        self._disabled.discard(plugin_name)
        logger.info("Unloaded plugin: %s", plugin_name)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """Return info about all loaded plugins.

        Returns:
            List of dicts with name, version, active, and file_path.
        """
        result = []
        for name, plugin in self._plugins.items():
            result.append({
                "name": name,
                "version": plugin.version,
                "active": name not in self._disabled,
                "file_path": self._plugin_files.get(name, ""),
            })
        return result

    def get_plugin(self, name: str) -> HumanePlugin:
        """Get a loaded plugin by name.

        Args:
            name: Plugin name.

        Returns:
            The HumanePlugin instance.

        Raises:
            KeyError if plugin is not loaded.
        """
        if name not in self._plugins:
            raise KeyError(f"Plugin '{name}' is not loaded")
        return self._plugins[name]

    def toggle(self, name: str) -> bool:
        """Toggle a plugin between active and disabled.

        Returns:
            True if the plugin is now active, False if disabled.
        """
        if name not in self._plugins:
            raise KeyError(f"Plugin '{name}' is not loaded")

        if name in self._disabled:
            self._disabled.discard(name)
            return True
        else:
            self._disabled.add(name)
            return False

    def get_active_plugins(self) -> List[HumanePlugin]:
        """Return all loaded and active (not disabled) plugins."""
        return [
            p for name, p in self._plugins.items()
            if name not in self._disabled
        ]

    def discover_and_load_all(self) -> int:
        """Convenience: discover all plugins in plugins_dir and load them.

        Returns:
            Number of plugins loaded.
        """
        discovered = self.discover()
        loaded = 0
        for info in discovered:
            try:
                self.load(info["class"])
                self._plugin_files[info["name"]] = info["file_path"]
                loaded += 1
            except Exception as e:
                logger.warning("Failed to load plugin %s: %s", info["name"], e)
        return loaded
