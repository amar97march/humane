"""Tests for configuration management."""

import os
import tempfile
import pytest

from humane.core.config import (
    HumaneConfig,
    validate_config,
    save_config,
    load_config,
)


class TestConfigDefaults:
    def test_defaults_valid(self):
        config = HumaneConfig()
        validate_config(config)

    def test_all_defaults_present(self):
        config = HumaneConfig()
        assert config.impulse_base_rate_per_day == 4.0
        assert config.confidence_threshold == 0.65
        assert config.fatigue_defer_threshold == 0.80
        assert config.dissent_threshold == 0.60
        assert config.social_risk_block_threshold == 0.65
        assert config.anomaly_hard_threshold == 0.60


class TestConfigValidation:
    def test_negative_impulse_rate(self):
        config = HumaneConfig(impulse_base_rate_per_day=-1)
        with pytest.raises(ValueError):
            validate_config(config)

    def test_threshold_out_of_range(self):
        config = HumaneConfig(confidence_threshold=1.5)
        with pytest.raises(ValueError):
            validate_config(config)

    def test_flag_above_block(self):
        config = HumaneConfig(
            social_risk_flag_threshold=0.8,
            social_risk_block_threshold=0.5,
        )
        with pytest.raises(ValueError):
            validate_config(config)

    def test_empty_agent_name(self):
        config = HumaneConfig(agent_name="")
        with pytest.raises(ValueError):
            validate_config(config)


class TestConfigSaveLoad:
    def test_roundtrip(self):
        config = HumaneConfig(agent_name="test-agent", impulse_base_rate_per_day=8.0)
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name
        try:
            save_config(config, path)
            loaded = load_config(path)
            assert loaded.agent_name == "test-agent"
            assert loaded.impulse_base_rate_per_day == 8.0
        finally:
            os.unlink(path)

    def test_load_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            load_config("/tmp/nonexistent_humane.yaml")
