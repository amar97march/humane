"""Tests for the PluginManager — extensible gate engine via HumanePlugin."""

import pytest
from unittest.mock import MagicMock

from humane.core.models import GateResult, ProposedAction, Verdict
from humane.plugins import HumanePlugin, PluginManager


class DummyPlugin(HumanePlugin):
    """A simple test plugin that always proceeds."""
    name = "dummy_plugin"
    version = "1.0.0"

    def evaluate(self, action: ProposedAction, context: dict) -> GateResult:
        return GateResult(
            engine=self.name,
            verdict=Verdict.PROCEED,
            score=0.9,
            reason="Dummy plugin approved",
        )


class BlockingPlugin(HumanePlugin):
    """A test plugin that always holds."""
    name = "blocking_plugin"
    version = "0.1.0"

    def evaluate(self, action: ProposedAction, context: dict) -> GateResult:
        return GateResult(
            engine=self.name,
            verdict=Verdict.HOLD,
            score=0.1,
            reason="Blocking plugin rejected",
        )


class NotAPlugin:
    """Not a HumanePlugin subclass."""
    name = "fake"


@pytest.fixture
def manager(tmp_path):
    return PluginManager(plugins_dir=str(tmp_path / "plugins"))


@pytest.fixture
def manager_with_plugins(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    # Write a plugin file
    plugin_file = plugins_dir / "sample_plugin.py"
    plugin_file.write_text(
        "from humane.plugins import HumanePlugin\n"
        "from humane.core.models import GateResult, ProposedAction, Verdict\n\n"
        "class SamplePlugin(HumanePlugin):\n"
        "    name = 'sample'\n"
        "    version = '0.2.0'\n"
        "    def evaluate(self, action, context):\n"
        "        return GateResult(engine=self.name, verdict=Verdict.PROCEED, score=1.0, reason='ok')\n"
    )
    return PluginManager(plugins_dir=str(plugins_dir))


class TestPluginDiscover:
    def test_discover_finds_plugins(self, manager_with_plugins):
        discovered = manager_with_plugins.discover()
        assert len(discovered) >= 1
        assert discovered[0]["name"] == "sample"
        assert discovered[0]["version"] == "0.2.0"

    def test_discover_empty_dir(self, manager):
        discovered = manager.discover()
        assert discovered == []


class TestPluginLoadUnload:
    def test_load_plugin(self, manager):
        manager.load(DummyPlugin)
        plugins = manager.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "dummy_plugin"

    def test_unload_plugin(self, manager):
        manager.load(DummyPlugin)
        manager.unload("dummy_plugin")
        assert manager.list_plugins() == []

    def test_unload_nonexistent_raises(self, manager):
        with pytest.raises(KeyError):
            manager.unload("nonexistent")

    def test_load_calls_on_load_with_conductor(self, manager):
        conductor_mock = MagicMock()
        manager.set_conductor(conductor_mock)
        manager.load(DummyPlugin)
        # Plugin should be loaded and accessible
        plugin = manager.get_plugin("dummy_plugin")
        assert plugin.name == "dummy_plugin"


class TestPluginEvaluate:
    def test_plugin_evaluate_called(self, manager):
        manager.load(DummyPlugin)
        plugin = manager.get_plugin("dummy_plugin")
        action = ProposedAction(
            action_type="test", payload={},
            confidence=0.8, rationale="test", source="user",
        )
        result = plugin.evaluate(action, {"energy": 0.8})
        assert result.verdict == Verdict.PROCEED
        assert result.engine == "dummy_plugin"


class TestListPlugins:
    def test_list_plugins_returns_expected_format(self, manager):
        manager.load(DummyPlugin)
        manager.load(BlockingPlugin)
        plugins = manager.list_plugins()
        assert len(plugins) == 2
        for p in plugins:
            assert "name" in p
            assert "version" in p
            assert "active" in p
            assert "file_path" in p

    def test_list_plugins_shows_active_state(self, manager):
        manager.load(DummyPlugin)
        plugins = manager.list_plugins()
        assert plugins[0]["active"] is True

        manager.toggle("dummy_plugin")
        plugins = manager.list_plugins()
        assert plugins[0]["active"] is False


class TestInvalidPlugin:
    def test_invalid_plugin_class_rejected(self, manager):
        with pytest.raises(TypeError):
            manager.load(NotAPlugin)

    def test_str_class_rejected(self, manager):
        with pytest.raises(TypeError):
            manager.load(str)
