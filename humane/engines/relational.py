from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from humane.core.models import (
    EntityState,
    EntityType,
    RelationshipHealth,
    TrustLevel,
)


class Store(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any) -> None: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


class RelationalMemoryEngine:
    STORE_KEY = "relational_memory"

    ENTITY_DECAY_RATES: Dict[EntityType, Dict[str, float]] = {
        EntityType.CLOSE_COLLEAGUE: {"sentiment_half_life": 60, "grudge_half_life": 120},
        EntityType.CLIENT: {"sentiment_half_life": 30, "grudge_half_life": 90},
        EntityType.PROSPECT: {"sentiment_half_life": 14, "grudge_half_life": 45},
        EntityType.VENDOR: {"sentiment_half_life": 21, "grudge_half_life": 60},
        EntityType.UNKNOWN: {"sentiment_half_life": 7, "grudge_half_life": 30},
    }

    TRUST_DISCLOSURE: Dict[TrustLevel, float] = {
        TrustLevel.DEEP_TRUST: 0.30,
        TrustLevel.TRUSTED: 0.50,
        TrustLevel.NEUTRAL: 0.70,
        TrustLevel.CAUTIOUS: 0.85,
        TrustLevel.UNTRUSTED: 1.00,
    }

    def __init__(self, config: Any, store: Store, event_log: EventLog) -> None:
        self.config = config
        self.store = store
        self.event_log = event_log
        self._entities: Dict[str, EntityState] = {}
        self._interaction_log: Dict[str, List[Dict[str, Any]]] = {}
        self._load()

    def add_entity(
        self, name: str, entity_type: EntityType = EntityType.UNKNOWN
    ) -> EntityState:
        entity_id = str(uuid4())
        entity = EntityState(
            entity_id=entity_id,
            name=name,
            entity_type=entity_type,
            created_at=time.time(),
        )
        self._entities[entity_id] = entity
        self._interaction_log[entity_id] = []
        self._save()
        self.event_log.log("entity_added", "relational", {
            "entity_id": entity_id,
            "name": name,
            "type": entity_type.value,
        })
        return entity

    def get_entity(self, entity_id: str) -> Optional[EntityState]:
        entity = self._entities.get(entity_id)
        if entity is not None:
            self._apply_decay(entity)
        return entity

    def list_entities(self) -> List[EntityState]:
        for entity in self._entities.values():
            self._apply_decay(entity)
        return list(self._entities.values())

    def log_interaction(self, entity_id: str, sentiment: float, summary: str) -> None:
        entity = self._entities.get(entity_id)
        if entity is None:
            return

        self._apply_decay(entity)

        weight = 1.0 / (entity.interaction_count + 1)
        entity.sentiment_score = (
            entity.sentiment_score * (1 - weight) + sentiment * weight
        )
        entity.sentiment_score = max(-1.0, min(1.0, entity.sentiment_score))

        if sentiment < -0.2:
            grudge_increment = abs(sentiment) * 0.3
            entity.grudge_score = min(1.0, entity.grudge_score + grudge_increment)

        entity.interaction_count += 1
        entity.last_interaction_at = time.time()

        entity.trust_level = self._derive_trust_level(entity)
        entity.relationship_health = self._derive_health(entity)
        entity.disclosure_threshold = self.TRUST_DISCLOSURE.get(
            entity.trust_level, 0.70
        )

        self._interaction_log.setdefault(entity_id, []).append({
            "sentiment": sentiment,
            "summary": summary,
            "timestamp": time.time(),
        })

        self._save()
        self.event_log.log("interaction_logged", "relational", {
            "entity_id": entity_id,
            "sentiment": sentiment,
            "trust_level": entity.trust_level.value,
            "health": entity.relationship_health.value,
        })

    def _apply_decay(self, entity: EntityState) -> None:
        if entity.last_interaction_at is None:
            return

        days_since = (time.time() - entity.last_interaction_at) / 86400
        if days_since <= 0:
            return

        rates = self.ENTITY_DECAY_RATES.get(
            entity.entity_type, self.ENTITY_DECAY_RATES[EntityType.UNKNOWN]
        )

        sentiment_lambda = math.log(2) / rates["sentiment_half_life"]
        entity.sentiment_score *= math.exp(-sentiment_lambda * days_since)

        grudge_lambda = math.log(2) / rates["grudge_half_life"]
        entity.grudge_score *= math.exp(-grudge_lambda * days_since)

        entity.sentiment_score = max(-1.0, min(1.0, entity.sentiment_score))
        entity.grudge_score = max(0.0, min(1.0, entity.grudge_score))

    def _derive_trust_level(self, entity: EntityState) -> TrustLevel:
        score = entity.sentiment_score - (entity.grudge_score * 0.5)

        if score > 0.6 and entity.interaction_count >= 10:
            return TrustLevel.DEEP_TRUST
        if score > 0.3 and entity.interaction_count >= 5:
            return TrustLevel.TRUSTED
        if score > -0.1:
            return TrustLevel.NEUTRAL
        if score > -0.4:
            return TrustLevel.CAUTIOUS
        return TrustLevel.UNTRUSTED

    def _derive_health(self, entity: EntityState) -> RelationshipHealth:
        sentiment = entity.sentiment_score
        grudge = entity.grudge_score

        if grudge > 0.7 or sentiment < -0.5:
            return RelationshipHealth.BROKEN
        if grudge > 0.4 or sentiment < -0.2:
            return RelationshipHealth.STRAINED
        if grudge > 0.2 or sentiment < 0.1:
            return RelationshipHealth.FRAGILE
        if sentiment > 0.4 and grudge < 0.1:
            return RelationshipHealth.STRONG
        return RelationshipHealth.STABLE

    def get_disclosure_threshold(self, entity_id: str) -> float:
        entity = self._entities.get(entity_id)
        if entity is None:
            return 1.0
        return self.TRUST_DISCLOSURE.get(entity.trust_level, 0.70)

    def get_context(self, entity_id: str) -> Dict[str, Any]:
        entity = self.get_entity(entity_id)
        if entity is None:
            return {}

        recent_interactions = self._interaction_log.get(entity_id, [])[-5:]

        return {
            "entity_id": entity.entity_id,
            "name": entity.name,
            "entity_type": entity.entity_type.value,
            "sentiment_score": round(entity.sentiment_score, 3),
            "grudge_score": round(entity.grudge_score, 3),
            "trust_level": entity.trust_level.value,
            "relationship_health": entity.relationship_health.value,
            "disclosure_threshold": entity.disclosure_threshold,
            "interaction_count": entity.interaction_count,
            "last_interaction_at": entity.last_interaction_at,
            "recent_interactions": recent_interactions,
        }

    def _save(self) -> None:
        entities_data: Dict[str, Dict[str, Any]] = {}
        for eid, e in self._entities.items():
            entities_data[eid] = {
                "entity_id": e.entity_id,
                "name": e.name,
                "entity_type": e.entity_type.value,
                "sentiment_score": e.sentiment_score,
                "grudge_score": e.grudge_score,
                "trust_level": e.trust_level.value,
                "relationship_health": e.relationship_health.value,
                "disclosure_threshold": e.disclosure_threshold,
                "interaction_count": e.interaction_count,
                "last_interaction_at": e.last_interaction_at,
                "created_at": e.created_at,
            }
        self.store.set(self.STORE_KEY, {
            "entities": entities_data,
            "interaction_log": self._interaction_log,
        })

    def _load(self) -> None:
        data = self.store.get(self.STORE_KEY)
        if data is None:
            return

        for eid, ed in data.get("entities", {}).items():
            self._entities[eid] = EntityState(
                entity_id=ed["entity_id"],
                name=ed["name"],
                entity_type=EntityType(ed["entity_type"]),
                sentiment_score=ed.get("sentiment_score", 0.0),
                grudge_score=ed.get("grudge_score", 0.0),
                trust_level=TrustLevel(ed.get("trust_level", "neutral")),
                relationship_health=RelationshipHealth(ed.get("relationship_health", "stable")),
                disclosure_threshold=ed.get("disclosure_threshold", 0.7),
                interaction_count=ed.get("interaction_count", 0),
                last_interaction_at=ed.get("last_interaction_at"),
                created_at=ed.get("created_at", time.time()),
            )

        self._interaction_log = data.get("interaction_log", {})
