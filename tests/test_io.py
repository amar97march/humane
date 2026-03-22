"""Tests for Import/Export — bundle serialization, validation, merge vs replace."""

import os
import tempfile
import time
import pytest

from humane.conductor import Conductor
from humane.core.config import HumaneConfig
from humane.core.models import EntityType, MemoryType, ValueSeverity
from humane.io import export_bundle, import_bundle, SENSITIVE_CONFIG_KEYS, _validate_bundle


_io_counter = 0


def _make_conductor(db_path=None):
    global _io_counter
    if db_path is None:
        _io_counter += 1
        db_path = os.path.join(tempfile.gettempdir(), f"test_io_{os.getpid()}_{_io_counter}.db")
    config = HumaneConfig()
    config.db_path = db_path
    config.llm_api_key = "sk-secret-key-12345"
    config.telegram_bot_token = "telegram-secret-token"
    return Conductor(config=config, db_path=db_path), config


class TestExportBundle:
    def test_export_produces_all_sections(self):
        conductor, config = _make_conductor()
        bundle = export_bundle(conductor, config)
        assert "config" in bundle
        assert "entities" in bundle
        assert "goals" in bundle
        assert "memories" in bundle
        assert "values" in bundle
        assert "human_state" in bundle
        assert "metadata" in bundle

    def test_export_metadata_contains_version(self):
        conductor, config = _make_conductor()
        bundle = export_bundle(conductor, config)
        assert "export_version" in bundle["metadata"]
        assert "exported_at" in bundle["metadata"]
        assert "agent_name" in bundle["metadata"]

    def test_export_excludes_api_keys(self):
        conductor, config = _make_conductor()
        bundle = export_bundle(conductor, config)
        for key in SENSITIVE_CONFIG_KEYS:
            assert key not in bundle["config"]

    def test_export_excludes_llm_api_key(self):
        conductor, config = _make_conductor()
        bundle = export_bundle(conductor, config)
        assert "llm_api_key" not in bundle["config"]

    def test_export_excludes_telegram_bot_token(self):
        conductor, config = _make_conductor()
        bundle = export_bundle(conductor, config)
        assert "telegram_bot_token" not in bundle["config"]

    def test_export_includes_entities(self):
        conductor, config = _make_conductor()
        conductor.relational.add_entity("Arjun", EntityType.PROSPECT)
        bundle = export_bundle(conductor, config)
        assert len(bundle["entities"]) == 1
        assert bundle["entities"][0]["name"] == "Arjun"

    def test_export_includes_memories(self):
        conductor, config = _make_conductor()
        conductor.memory_decay.add_memory(MemoryType.EPISODIC, "Met Arjun at coffee shop")
        bundle = export_bundle(conductor, config)
        assert len(bundle["memories"]) >= 1
        assert any("Arjun" in m["content"] for m in bundle["memories"])

    def test_export_includes_goals(self):
        conductor, config = _make_conductor()
        conductor.goal_engine.register_goal("Close the deal")
        bundle = export_bundle(conductor, config)
        assert len(bundle["goals"]) == 1
        assert bundle["goals"][0]["description"] == "Close the deal"

    def test_export_human_state_snapshot(self):
        conductor, config = _make_conductor()
        bundle = export_bundle(conductor, config)
        state = bundle["human_state"]
        assert "energy" in state
        assert "mood" in state
        assert "fatigue" in state

    def test_export_is_json_serializable(self):
        import json
        conductor, config = _make_conductor()
        conductor.relational.add_entity("Test", EntityType.CLOSE_COLLEAGUE)
        conductor.goal_engine.register_goal("Test goal")
        bundle = export_bundle(conductor, config)
        # Should not raise
        serialized = json.dumps(bundle, default=str)
        assert isinstance(serialized, str)


class TestValidateBundle:
    def test_valid_bundle_has_no_errors(self):
        bundle = {
            "metadata": {"export_version": "1.0"},
            "entities": [],
            "goals": [],
            "memories": [],
            "values": [],
        }
        errors = _validate_bundle(bundle)
        assert errors == []

    def test_missing_required_keys(self):
        bundle = {"metadata": {"export_version": "1.0"}}
        errors = _validate_bundle(bundle)
        assert len(errors) > 0
        assert any("Missing required keys" in e for e in errors)

    def test_non_dict_bundle(self):
        errors = _validate_bundle("not a dict")
        assert errors == ["Bundle must be a JSON object"]

    def test_missing_export_version(self):
        bundle = {
            "metadata": {},
            "entities": [],
            "goals": [],
            "memories": [],
            "values": [],
        }
        errors = _validate_bundle(bundle)
        assert any("export_version" in e for e in errors)

    def test_non_list_entities(self):
        bundle = {
            "metadata": {"export_version": "1.0"},
            "entities": "not a list",
            "goals": [],
            "memories": [],
            "values": [],
        }
        errors = _validate_bundle(bundle)
        assert any("entities must be an array" in e for e in errors)


class TestImportBundleReplace:
    def test_import_replace_clears_existing_data(self):
        conductor, config = _make_conductor()
        # Add existing data
        conductor.relational.add_entity("OldEntity", EntityType.PROSPECT)
        conductor.goal_engine.register_goal("Old goal")

        bundle = {
            "metadata": {"export_version": "1.0"},
            "entities": [
                {"name": "NewEntity", "entity_type": "prospect"}
            ],
            "goals": [
                {"description": "New goal", "expected_value": 0.9}
            ],
            "memories": [],
            "values": [],
        }
        result = import_bundle(conductor, config, bundle, merge_mode="replace")

        assert result["imported"]["entities"] == 1
        assert result["imported"]["goals"] == 1

        # Old data should be gone
        entities = conductor.relational.list_entities()
        entity_names = [e.name for e in entities]
        assert "OldEntity" not in entity_names
        assert "NewEntity" in entity_names

    def test_import_replace_reimports_all_sections(self):
        conductor, config = _make_conductor()
        bundle = {
            "metadata": {"export_version": "1.0"},
            "entities": [
                {"name": "Entity1", "entity_type": "prospect"},
                {"name": "Entity2", "entity_type": "close_colleague"},
            ],
            "goals": [
                {"description": "Goal1"},
            ],
            "memories": [
                {"content": "Memory1", "memory_type": "episodic"},
            ],
            "values": [
                {"description": "Never lie", "behavioral_pattern": "Honesty", "severity": "hard"},
            ],
        }
        result = import_bundle(conductor, config, bundle, merge_mode="replace")
        assert result["imported"]["entities"] == 2
        assert result["imported"]["goals"] == 1
        assert result["imported"]["memories"] == 1
        assert result["imported"]["values"] == 1
        assert result["skipped"] == 0


class TestImportBundleMerge:
    def test_import_merge_skips_duplicate_entities(self):
        conductor, config = _make_conductor()
        conductor.relational.add_entity("Arjun", EntityType.PROSPECT)

        bundle = {
            "metadata": {"export_version": "1.0"},
            "entities": [
                {"name": "Arjun", "entity_type": "prospect"},  # duplicate
                {"name": "Priya", "entity_type": "close_colleague"},  # new
            ],
            "goals": [],
            "memories": [],
            "values": [],
        }
        result = import_bundle(conductor, config, bundle, merge_mode="merge")
        assert result["imported"]["entities"] == 1
        assert result["skipped"] >= 1

    def test_import_merge_skips_duplicate_goals(self):
        conductor, config = _make_conductor()
        conductor.goal_engine.register_goal("Close deal")

        bundle = {
            "metadata": {"export_version": "1.0"},
            "entities": [],
            "goals": [
                {"description": "Close deal"},  # duplicate
                {"description": "New goal"},  # new
            ],
            "memories": [],
            "values": [],
        }
        result = import_bundle(conductor, config, bundle, merge_mode="merge")
        assert result["imported"]["goals"] == 1
        assert result["skipped"] >= 1

    def test_import_merge_skips_duplicate_memories(self):
        conductor, config = _make_conductor()
        conductor.memory_decay.add_memory(MemoryType.EPISODIC, "Met at coffee shop")

        bundle = {
            "metadata": {"export_version": "1.0"},
            "entities": [],
            "goals": [],
            "memories": [
                {"content": "Met at coffee shop", "memory_type": "episodic"},  # duplicate
                {"content": "New memory", "memory_type": "episodic"},  # new
            ],
            "values": [],
        }
        result = import_bundle(conductor, config, bundle, merge_mode="merge")
        assert result["imported"]["memories"] == 1
        assert result["skipped"] >= 1

    def test_import_merge_preserves_existing_data(self):
        conductor, config = _make_conductor()
        conductor.relational.add_entity("Existing", EntityType.PROSPECT)

        bundle = {
            "metadata": {"export_version": "1.0"},
            "entities": [
                {"name": "New", "entity_type": "close_colleague"},
            ],
            "goals": [],
            "memories": [],
            "values": [],
        }
        result = import_bundle(conductor, config, bundle, merge_mode="merge")
        entities = conductor.relational.list_entities()
        entity_names = [e.name for e in entities]
        assert "Existing" in entity_names
        assert "New" in entity_names


class TestImportValidation:
    def test_import_invalid_bundle_returns_errors(self):
        conductor, config = _make_conductor()
        result = import_bundle(conductor, config, {"bad": "data"})
        assert len(result["errors"]) > 0
        assert result["imported"] == {}

    def test_import_non_dict_returns_errors(self):
        conductor, config = _make_conductor()
        result = import_bundle(conductor, config, "not a dict")
        assert len(result["errors"]) > 0

    def test_import_does_not_set_sensitive_config_keys(self):
        conductor, config = _make_conductor()
        original_key = config.llm_api_key
        bundle = {
            "metadata": {"export_version": "1.0"},
            "config": {"llm_api_key": "injected-key"},
            "entities": [],
            "goals": [],
            "memories": [],
            "values": [],
        }
        import_bundle(conductor, config, bundle, merge_mode="replace")
        # Sensitive keys should not be overwritten
        assert config.llm_api_key == original_key
