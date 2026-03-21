from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class Verdict(Enum):
    PROCEED = "proceed"
    HOLD = "hold"
    DEFER = "defer"


class ImpulseType(Enum):
    RETROACTIVE_REVIEW = "retroactive_review"
    IDLE_DISCOVERY = "idle_discovery"
    RANDOM_NUDGE = "random_nudge"
    CROSS_DOMAIN_SPARK = "cross_domain_spark"
    GOAL_REASSESSMENT = "goal_reassessment"
    DISSENT_FLASH = "dissent_flash"


class EntityType(Enum):
    CLOSE_COLLEAGUE = "close_colleague"
    CLIENT = "client"
    PROSPECT = "prospect"
    VENDOR = "vendor"
    UNKNOWN = "unknown"


class TrustLevel(Enum):
    UNTRUSTED = "untrusted"
    CAUTIOUS = "cautious"
    NEUTRAL = "neutral"
    TRUSTED = "trusted"
    DEEP_TRUST = "deep_trust"


class RelationshipHealth(Enum):
    BROKEN = "broken"
    STRAINED = "strained"
    FRAGILE = "fragile"
    STABLE = "stable"
    STRONG = "strong"


class MemoryType(Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    RELATIONAL = "relational"
    PROCEDURAL = "procedural"


class ValueSeverity(Enum):
    SOFT = "soft"
    HARD = "hard"


class TaskType(Enum):
    CREATIVE_OR_STRATEGIC = "creative_or_strategic"
    MECHANICAL_OR_ROUTINE = "mechanical_or_routine"
    SOLO_ANALYTICAL = "solo_analytical"
    LOW_INTERACTION_FOCUSED = "low_interaction_focused"
    ANY = "any"


@dataclass
class ProposedAction:
    action_type: str
    payload: Dict
    confidence: float
    rationale: str
    source: str
    target_entity: Optional[str] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class HoldItem:
    id: str = field(default_factory=lambda: str(uuid4()))
    action: ProposedAction = field(default_factory=lambda: ProposedAction("", {}, 0.0, "", ""))
    adjusted_confidence: float = 0.0
    hold_reason: str = ""
    hold_source: str = ""
    verdict: Verdict = Verdict.HOLD
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    resolved: bool = False
    resolution: Optional[str] = None


@dataclass
class GateResult:
    engine: str
    verdict: Verdict
    score: float
    reason: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class EvaluationResult:
    action: ProposedAction
    final_verdict: Verdict
    gate_results: List[GateResult]
    hold_item: Optional[HoldItem] = None
    audit_trail: List[str] = field(default_factory=list)


@dataclass
class ValueStatement:
    id: str
    description: str
    behavioral_pattern: str
    violation_examples: List[str] = field(default_factory=list)
    honoring_examples: List[str] = field(default_factory=list)
    severity: ValueSeverity = ValueSeverity.SOFT


@dataclass
class EntityState:
    entity_id: str
    name: str
    entity_type: EntityType = EntityType.UNKNOWN
    sentiment_score: float = 0.0
    grudge_score: float = 0.0
    trust_level: TrustLevel = TrustLevel.NEUTRAL
    relationship_health: RelationshipHealth = RelationshipHealth.STABLE
    disclosure_threshold: float = 0.7
    interaction_count: int = 0
    last_interaction_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class Goal:
    id: str
    description: str
    expected_value: float = 1.0
    remaining_effort: float = 1.0
    progress_velocity: float = 0.0
    relevance_decay: float = 1.0
    milestones_total: int = 0
    milestones_completed: int = 0
    created_at: float = field(default_factory=time.time)
    last_evaluated_at: Optional[float] = None
    status: str = "active"


@dataclass
class Memory:
    id: str
    memory_type: MemoryType
    content: str
    relevance_score: float = 1.0
    access_count: int = 0
    pinned: bool = False
    created_at: float = field(default_factory=time.time)
    last_accessed_at: Optional[float] = None
    archived: bool = False


@dataclass
class ImpulseEvent:
    id: str
    impulse_type: ImpulseType
    payload: Dict = field(default_factory=dict)
    state_snapshot: Dict = field(default_factory=dict)
    outcome: Optional[str] = None
    created_at: float = field(default_factory=time.time)
