from __future__ import annotations

import time
from typing import Any, Dict, Optional, Protocol

from humane.core.config import HumaneConfig
from humane.core.models import (
    EntityState,
    EntityType,
    GateResult,
    ProposedAction,
    RelationshipHealth,
    Verdict,
)


class RelationalEngine(Protocol):
    def get_entity(self, entity_id: str) -> Optional[EntityState]: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


AGGRESSIVE_WORDS = [
    "urgent", "immediately", "demand", "require", "must",
    "asap", "overdue", "final notice", "last chance", "warning",
]

PUBLIC_ACTION_KEYWORDS = ["post", "announce", "publish", "broadcast", "tweet", "share"]


class SocialRiskEngine:
    WEIGHTS: Dict[str, float] = {
        "power_differential": 0.20,
        "relationship_health": 0.25,
        "action_visibility": 0.15,
        "tone_analysis": 0.20,
        "contact_frequency": 0.10,
        "contextual_appropriateness": 0.10,
    }

    HEALTH_RISK_MAP: Dict[RelationshipHealth, float] = {
        RelationshipHealth.BROKEN: 1.0,
        RelationshipHealth.STRAINED: 0.8,
        RelationshipHealth.FRAGILE: 0.5,
        RelationshipHealth.STABLE: 0.2,
        RelationshipHealth.STRONG: 0.1,
    }

    def __init__(
        self,
        config: HumaneConfig,
        relational_engine: RelationalEngine,
        event_log: EventLog,
    ) -> None:
        self.config = config
        self.relational = relational_engine
        self.event_log = event_log

    def evaluate(self, action: ProposedAction) -> GateResult:
        score = self._compute_risk_score(action)

        if score > self.config.social_risk_block_threshold:
            result = GateResult(
                engine="social_risk",
                verdict=Verdict.HOLD,
                score=score,
                reason=f"Social risk {score:.2f} above block threshold",
            )
        elif score > self.config.social_risk_flag_threshold:
            result = GateResult(
                engine="social_risk",
                verdict=Verdict.PROCEED,
                score=score,
                reason=f"Social risk {score:.2f} -- flagged",
                metadata={"flagged": True},
            )
        else:
            result = GateResult(
                engine="social_risk",
                verdict=Verdict.PROCEED,
                score=score,
                reason="Social risk acceptable",
            )

        self.event_log.log("social_risk_evaluation", "social_risk", {
            "verdict": result.verdict.value,
            "score": round(score, 4),
            "action_type": action.action_type,
            "target_entity": action.target_entity,
        })

        return result

    def _compute_risk_score(self, action: ProposedAction) -> float:
        score = 0.0
        entity: Optional[EntityState] = None

        if action.target_entity:
            entity = self.relational.get_entity(action.target_entity)

        score += self._score_power_differential(entity)
        score += self._score_relationship_health(entity)
        score += self._score_action_visibility(action)
        score += self._score_tone(action)
        score += self._score_contact_frequency(entity)
        score += self._score_contextual_appropriateness(action, entity)

        return max(0.0, min(1.0, score))

    def _score_power_differential(self, entity: Optional[EntityState]) -> float:
        if entity is None:
            return self.WEIGHTS["power_differential"] * 0.3

        type_risk: Dict[EntityType, float] = {
            EntityType.CLIENT: 0.7,
            EntityType.PROSPECT: 0.6,
            EntityType.VENDOR: 0.3,
            EntityType.CLOSE_COLLEAGUE: 0.2,
            EntityType.UNKNOWN: 0.5,
        }
        return self.WEIGHTS["power_differential"] * type_risk.get(entity.entity_type, 0.3)

    def _score_relationship_health(self, entity: Optional[EntityState]) -> float:
        if entity is None:
            return self.WEIGHTS["relationship_health"] * 0.3

        risk = self.HEALTH_RISK_MAP.get(entity.relationship_health, 0.3)
        return self.WEIGHTS["relationship_health"] * risk

    def _score_action_visibility(self, action: ProposedAction) -> float:
        action_lower = action.action_type.lower()
        payload_lower = str(action.payload).lower()
        combined = action_lower + " " + payload_lower

        is_public = any(kw in combined for kw in PUBLIC_ACTION_KEYWORDS)
        return self.WEIGHTS["action_visibility"] * (0.8 if is_public else 0.2)

    def _score_tone(self, action: ProposedAction) -> float:
        text = f"{action.action_type} {action.rationale} {str(action.payload)}".lower()
        tone_hits = sum(1 for w in AGGRESSIVE_WORDS if w in text)
        tone_score = min(1.0, tone_hits * 0.15)
        return self.WEIGHTS["tone_analysis"] * tone_score

    def _score_contact_frequency(self, entity: Optional[EntityState]) -> float:
        if entity is None or entity.last_interaction_at is None:
            return 0.0

        days_since = (time.time() - entity.last_interaction_at) / 86400

        if days_since < 1:
            freq_risk = 0.8
        elif days_since < 3:
            freq_risk = 0.4
        elif days_since < 7:
            freq_risk = 0.2
        else:
            freq_risk = 0.1

        return self.WEIGHTS["contact_frequency"] * freq_risk

    def _score_contextual_appropriateness(
        self, action: ProposedAction, entity: Optional[EntityState]
    ) -> float:
        base = 0.2
        if entity and entity.relationship_health == RelationshipHealth.BROKEN:
            base = 0.7
        return self.WEIGHTS["contextual_appropriateness"] * base
