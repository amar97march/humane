"""Humane Import/Export — full bundle serialization and deserialization."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from humane.core.config import HumaneConfig
from humane.core.models import (
    EntityState,
    EntityType,
    Goal,
    Memory,
    MemoryType,
    RelationshipHealth,
    TrustLevel,
    ValueSeverity,
    ValueStatement,
)

EXPORT_VERSION = "1.0"

SENSITIVE_CONFIG_KEYS = frozenset({
    "llm_api_key",
    "telegram_bot_token",
})


def export_bundle(conductor, config: HumaneConfig) -> dict:
    """Export everything as a JSON-serializable dict.

    Includes config (sans sensitive keys), entities, goals, memories,
    values, human_state snapshot, and metadata.
    """
    # Config — strip sensitive keys
    config_data = asdict(config)
    for key in SENSITIVE_CONFIG_KEYS:
        config_data.pop(key, None)

    # Entities
    entities = []
    for entity in conductor.relational.list_entities():
        entities.append({
            "entity_id": entity.entity_id,
            "name": entity.name,
            "entity_type": entity.entity_type.value,
            "sentiment_score": entity.sentiment_score,
            "grudge_score": entity.grudge_score,
            "trust_level": entity.trust_level.value,
            "relationship_health": entity.relationship_health.value,
            "disclosure_threshold": entity.disclosure_threshold,
            "interaction_count": entity.interaction_count,
            "last_interaction_at": entity.last_interaction_at,
            "created_at": entity.created_at,
        })

    # Goals
    goals = []
    for goal in conductor.goal_engine._goals.values():
        goals.append({
            "id": goal.id,
            "description": goal.description,
            "expected_value": goal.expected_value,
            "remaining_effort": goal.remaining_effort,
            "progress_velocity": goal.progress_velocity,
            "relevance_decay": goal.relevance_decay,
            "milestones_total": goal.milestones_total,
            "milestones_completed": goal.milestones_completed,
            "created_at": goal.created_at,
            "last_evaluated_at": goal.last_evaluated_at,
            "status": goal.status,
        })

    # Memories — both active and archived
    memories = []
    for memory in conductor.memory_decay._memories.values():
        memories.append({
            "id": memory.id,
            "memory_type": memory.memory_type.value,
            "content": memory.content,
            "relevance_score": memory.relevance_score,
            "access_count": memory.access_count,
            "pinned": memory.pinned,
            "created_at": memory.created_at,
            "last_accessed_at": memory.last_accessed_at,
            "archived": memory.archived,
        })

    # Values
    values = []
    for v in conductor.values.get_values():
        values.append({
            "id": v.id,
            "description": v.description,
            "behavioral_pattern": v.behavioral_pattern,
            "violation_examples": v.violation_examples,
            "honoring_examples": v.honoring_examples,
            "severity": v.severity.value,
        })

    # Human state
    human_state = conductor.human_state.snapshot()

    return {
        "config": config_data,
        "entities": entities,
        "goals": goals,
        "memories": memories,
        "values": values,
        "human_state": human_state,
        "metadata": {
            "export_version": EXPORT_VERSION,
            "exported_at": time.time(),
            "agent_name": config.agent_name,
        },
    }


def _validate_bundle(bundle: dict) -> List[str]:
    """Validate bundle format. Returns list of error messages (empty = valid)."""
    errors: List[str] = []

    if not isinstance(bundle, dict):
        return ["Bundle must be a JSON object"]

    required_keys = {"metadata", "entities", "goals", "memories", "values"}
    missing = required_keys - set(bundle.keys())
    if missing:
        errors.append(f"Missing required keys: {', '.join(sorted(missing))}")

    metadata = bundle.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            errors.append("metadata must be an object")
        elif "export_version" not in metadata:
            errors.append("metadata.export_version is required")

    for key in ("entities", "goals", "memories", "values"):
        val = bundle.get(key)
        if val is not None and not isinstance(val, list):
            errors.append(f"{key} must be an array")

    return errors


def import_bundle(
    conductor,
    config: HumaneConfig,
    bundle: dict,
    merge_mode: str = "replace",
) -> dict:
    """Import a bundle into the conductor.

    Args:
        conductor: The Conductor instance.
        config: The HumaneConfig instance.
        bundle: The bundle dict (from export_bundle or loaded from JSON).
        merge_mode: "replace" clears existing data first;
                     "merge" adds new items, skipping duplicates.

    Returns:
        Dict with imported counts, skipped count, and error list.
    """
    errors = _validate_bundle(bundle)
    if errors:
        return {"imported": {}, "skipped": 0, "errors": errors}

    imported = {"entities": 0, "goals": 0, "memories": 0, "values": 0}
    skipped = 0
    import_errors: List[str] = []

    # --- Config (non-sensitive fields only) ---
    bundle_config = bundle.get("config")
    if bundle_config and isinstance(bundle_config, dict):
        from dataclasses import fields as dc_fields
        valid_fields = {f.name for f in dc_fields(HumaneConfig)}
        for key, value in bundle_config.items():
            if key in valid_fields and key not in SENSITIVE_CONFIG_KEYS:
                try:
                    setattr(config, key, value)
                except Exception:
                    pass

    # --- Replace mode: clear existing data ---
    if merge_mode == "replace":
        conductor.relational._entities.clear()
        conductor.relational._interaction_log.clear()
        conductor.relational._save()

        conductor.goal_engine._goals.clear()
        conductor.goal_engine._save()

        conductor.memory_decay._memories.clear()
        conductor.memory_decay._save()

        conductor.values._values.clear()
        conductor.values._save()

    # --- Entities ---
    existing_entity_names = {
        e.name.lower() for e in conductor.relational._entities.values()
    }
    for ed in bundle.get("entities", []):
        try:
            name = ed.get("name", "")
            if merge_mode == "merge" and name.lower() in existing_entity_names:
                skipped += 1
                continue

            entity_id = ed.get("entity_id", str(__import__("uuid").uuid4()))
            entity = EntityState(
                entity_id=entity_id,
                name=name,
                entity_type=EntityType(ed.get("entity_type", "unknown")),
                sentiment_score=ed.get("sentiment_score", 0.0),
                grudge_score=ed.get("grudge_score", 0.0),
                trust_level=TrustLevel(ed.get("trust_level", "neutral")),
                relationship_health=RelationshipHealth(
                    ed.get("relationship_health", "stable")
                ),
                disclosure_threshold=ed.get("disclosure_threshold", 0.7),
                interaction_count=ed.get("interaction_count", 0),
                last_interaction_at=ed.get("last_interaction_at"),
                created_at=ed.get("created_at", time.time()),
            )
            conductor.relational._entities[entity_id] = entity
            conductor.relational._interaction_log.setdefault(entity_id, [])
            existing_entity_names.add(name.lower())
            imported["entities"] += 1
        except Exception as e:
            import_errors.append(f"Entity import error: {e}")

    conductor.relational._save()

    # --- Goals ---
    existing_goal_descriptions = {
        g.description.lower() for g in conductor.goal_engine._goals.values()
    }
    for gd in bundle.get("goals", []):
        try:
            desc = gd.get("description", "")
            if merge_mode == "merge" and desc.lower() in existing_goal_descriptions:
                skipped += 1
                continue

            goal_id = gd.get("id", str(__import__("uuid").uuid4()))
            goal = Goal(
                id=goal_id,
                description=desc,
                expected_value=gd.get("expected_value", 1.0),
                remaining_effort=gd.get("remaining_effort", 1.0),
                progress_velocity=gd.get("progress_velocity", 0.0),
                relevance_decay=gd.get("relevance_decay", 1.0),
                milestones_total=gd.get("milestones_total", 0),
                milestones_completed=gd.get("milestones_completed", 0),
                created_at=gd.get("created_at", time.time()),
                last_evaluated_at=gd.get("last_evaluated_at"),
                status=gd.get("status", "active"),
            )
            conductor.goal_engine._goals[goal_id] = goal
            existing_goal_descriptions.add(desc.lower())
            imported["goals"] += 1
        except Exception as e:
            import_errors.append(f"Goal import error: {e}")

    conductor.goal_engine._save()

    # --- Memories ---
    existing_memory_contents = {
        m.content.lower() for m in conductor.memory_decay._memories.values()
    }
    for md in bundle.get("memories", []):
        try:
            content = md.get("content", "")
            if merge_mode == "merge" and content.lower() in existing_memory_contents:
                skipped += 1
                continue

            mem_id = md.get("id", str(__import__("uuid").uuid4()))
            memory = Memory(
                id=mem_id,
                memory_type=MemoryType(md.get("memory_type", "episodic")),
                content=content,
                relevance_score=md.get("relevance_score", 1.0),
                access_count=md.get("access_count", 0),
                pinned=md.get("pinned", False),
                created_at=md.get("created_at", time.time()),
                last_accessed_at=md.get("last_accessed_at"),
                archived=md.get("archived", False),
            )
            conductor.memory_decay._memories[mem_id] = memory
            existing_memory_contents.add(content.lower())
            imported["memories"] += 1
        except Exception as e:
            import_errors.append(f"Memory import error: {e}")

    conductor.memory_decay._save()

    # --- Values ---
    existing_value_descriptions = {
        v.description.lower() for v in conductor.values._values
    }
    for vd in bundle.get("values", []):
        try:
            desc = vd.get("description", "")
            if merge_mode == "merge" and desc.lower() in existing_value_descriptions:
                skipped += 1
                continue

            value_id = vd.get("id", str(__import__("uuid").uuid4()))
            value = ValueStatement(
                id=value_id,
                description=desc,
                behavioral_pattern=vd.get("behavioral_pattern", ""),
                violation_examples=vd.get("violation_examples", []),
                honoring_examples=vd.get("honoring_examples", []),
                severity=ValueSeverity(vd.get("severity", "soft")),
            )
            conductor.values._values.append(value)
            existing_value_descriptions.add(desc.lower())
            imported["values"] += 1
        except Exception as e:
            import_errors.append(f"Value import error: {e}")

    conductor.values._save()

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": import_errors,
    }
