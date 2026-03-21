from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class HumaneConfig:
    impulse_base_rate_per_day: float = 4.0
    min_impulse_interval_mins: int = 20
    max_impulse_interval_mins: int = 480
    active_hours_start: int = 7
    active_hours_end: int = 22
    confidence_threshold: float = 0.65
    fatigue_defer_threshold: float = 0.80
    dissent_threshold: float = 0.60
    goal_abandon_roi_threshold: float = 0.25
    boredom_trigger_threshold: float = 0.70
    memory_retrieval_threshold: float = 0.30
    social_risk_block_threshold: float = 0.65
    social_risk_flag_threshold: float = 0.35
    anomaly_hard_threshold: float = 0.60
    anomaly_soft_threshold: float = 0.30
    agent_name: str = "humane-agent"
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    llm_api_key: str = ""
    llm_base_url: str = ""
    notification_channel: str = "none"
    db_path: str = "~/.humane/agent.db"
    values_preset: str = "business-safe"
    telegram_bot_token: str = ""
    api_port: int = 8765
    bot_personality: str = "colleague"
    reminder_base_interval_hours: float = 24.0
    max_escalation_level: int = 4


def validate_config(config: HumaneConfig) -> None:
    if config.impulse_base_rate_per_day < 0:
        raise ValueError("impulse_base_rate_per_day must be non-negative")
    if config.min_impulse_interval_mins < 1:
        raise ValueError("min_impulse_interval_mins must be at least 1")
    if config.max_impulse_interval_mins < config.min_impulse_interval_mins:
        raise ValueError("max_impulse_interval_mins must be >= min_impulse_interval_mins")
    if not (0 <= config.active_hours_start < 24):
        raise ValueError("active_hours_start must be in range [0, 24)")
    if not (0 < config.active_hours_end <= 24):
        raise ValueError("active_hours_end must be in range (0, 24]")
    if config.active_hours_start >= config.active_hours_end:
        raise ValueError("active_hours_start must be less than active_hours_end")

    threshold_fields = [
        "confidence_threshold",
        "fatigue_defer_threshold",
        "dissent_threshold",
        "goal_abandon_roi_threshold",
        "boredom_trigger_threshold",
        "memory_retrieval_threshold",
        "social_risk_block_threshold",
        "social_risk_flag_threshold",
        "anomaly_hard_threshold",
        "anomaly_soft_threshold",
    ]
    for name in threshold_fields:
        value = getattr(config, name)
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must be in range [0.0, 1.0], got {value}")

    if config.social_risk_flag_threshold >= config.social_risk_block_threshold:
        raise ValueError("social_risk_flag_threshold must be less than social_risk_block_threshold")
    if config.anomaly_soft_threshold >= config.anomaly_hard_threshold:
        raise ValueError("anomaly_soft_threshold must be less than anomaly_hard_threshold")

    if not config.agent_name.strip():
        raise ValueError("agent_name must not be empty")


def get_default_config_path(config: HumaneConfig | None = None) -> str:
    agent_name = config.agent_name if config else "humane-agent"
    return os.path.expanduser(f"~/.humane/{agent_name}.yaml")


def load_config(path: str) -> HumaneConfig:
    if yaml is None:
        raise ImportError("PyYAML is required for config loading. Install with: pip install pyyaml")

    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        raise FileNotFoundError(f"Config file not found: {expanded}")

    with open(expanded, "r") as f:
        raw = yaml.safe_load(f) or {}

    valid_fields = {fld.name for fld in fields(HumaneConfig)}
    filtered = {k: v for k, v in raw.items() if k in valid_fields}

    config = HumaneConfig(**filtered)
    validate_config(config)
    return config


def save_config(config: HumaneConfig, path: str) -> None:
    if yaml is None:
        raise ImportError("PyYAML is required for config saving. Install with: pip install pyyaml")

    expanded = os.path.expanduser(path)
    os.makedirs(os.path.dirname(expanded), exist_ok=True)

    validate_config(config)

    header = (
        "# Humane Agent Configuration\n"
        "# See documentation for parameter descriptions and valid ranges.\n"
        "#\n"
        "# Thresholds are floats in [0.0, 1.0].\n"
        "# Impulse intervals are in minutes.\n"
        "# Active hours use 24-hour format.\n"
        "\n"
    )

    data = asdict(config)

    with open(expanded, "w") as f:
        f.write(header)
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
