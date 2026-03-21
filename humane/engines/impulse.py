from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Any, Dict, Optional, Protocol
from uuid import uuid4

from humane.core.config import HumaneConfig
from humane.core.models import ImpulseEvent, ImpulseType


class HumanStateProtocol(Protocol):
    boredom: float
    energy: float
    fatigue: float
    mood: float
    def snapshot(self) -> Dict[str, Any]: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


IMPULSE_TEMPLATES: Dict[ImpulseType, str] = {
    ImpulseType.RETROACTIVE_REVIEW: "Review recent decisions for missed nuances or overlooked alternatives.",
    ImpulseType.IDLE_DISCOVERY: "Explore a tangential topic that may yield unexpected connections.",
    ImpulseType.RANDOM_NUDGE: "Surface a pending low-priority item for a quick check-in.",
    ImpulseType.CROSS_DOMAIN_SPARK: "Apply a concept from one domain to a problem in another.",
    ImpulseType.GOAL_REASSESSMENT: "Re-evaluate current goal priorities and trajectory.",
    ImpulseType.DISSENT_FLASH: "Challenge a recent assumption or default course of action.",
}


class StochasticImpulseEngine:
    def __init__(
        self, config: HumaneConfig, human_state: HumanStateProtocol, event_log: EventLog
    ) -> None:
        self.config = config
        self.human_state = human_state
        self.event_log = event_log
        self._last_fire_time: float = 0.0
        self._next_fire_time: float = self._schedule_next()

    def _effective_rate(self) -> float:
        base = self.config.impulse_base_rate_per_day / 24.0
        if self.human_state.boredom > self.config.boredom_trigger_threshold:
            boredom_boost = 1.0 + (self.human_state.boredom * 1.5)
        else:
            boredom_boost = 1.0
        energy_factor = max(0.2, self.human_state.energy)
        fatigue_suppress = max(0.3, 1.0 - self.human_state.fatigue)
        return base * boredom_boost * energy_factor * fatigue_suppress

    def _schedule_next(self) -> float:
        rate = self._effective_rate()
        if rate <= 0:
            return time.time() + 3600

        interval_hours = random.expovariate(rate)
        interval_mins = interval_hours * 60

        interval_mins = max(
            float(self.config.min_impulse_interval_mins),
            min(float(self.config.max_impulse_interval_mins), interval_mins),
        )

        jitter = random.gauss(1.0, 0.15)
        interval_mins *= max(0.5, jitter)

        return time.time() + (interval_mins * 60)

    def check_and_fire(self) -> Optional[ImpulseEvent]:
        now = time.time()
        hour = datetime.fromtimestamp(now).hour

        if hour < self.config.active_hours_start or hour >= self.config.active_hours_end:
            return None

        if now < self._next_fire_time:
            return None

        if now - self._last_fire_time < self.config.min_impulse_interval_mins * 60:
            return None

        impulse_type = self._select_type()
        payload = self._generate_payload(impulse_type)

        event = ImpulseEvent(
            id=str(uuid4()),
            impulse_type=impulse_type,
            payload=payload,
            state_snapshot=self.human_state.snapshot(),
            created_at=now,
        )

        self._last_fire_time = now
        self._next_fire_time = self._schedule_next()

        self.event_log.log(
            "impulse_fired", "impulse", {"type": impulse_type.value, "payload": payload}
        )

        return event

    def _select_type(self) -> ImpulseType:
        weights: Dict[ImpulseType, float] = {
            ImpulseType.RETROACTIVE_REVIEW: 1.0,
            ImpulseType.IDLE_DISCOVERY: 2.0 if self.human_state.boredom > 0.7 else 0.5,
            ImpulseType.RANDOM_NUDGE: 0.8,
            ImpulseType.CROSS_DOMAIN_SPARK: 1.5 if self.human_state.mood > 0.4 else 0.3,
            ImpulseType.GOAL_REASSESSMENT: 0.7,
            ImpulseType.DISSENT_FLASH: 1.2 if self.human_state.mood < -0.2 else 0.2,
        }
        types = list(weights.keys())
        w = [weights[t] for t in types]
        return random.choices(types, weights=w, k=1)[0]

    def _generate_payload(self, impulse_type: ImpulseType) -> Dict[str, Any]:
        return {
            "type": impulse_type.value,
            "prompt": IMPULSE_TEMPLATES.get(impulse_type, ""),
            "state_context": {
                "boredom": round(self.human_state.boredom, 3),
                "energy": round(self.human_state.energy, 3),
                "mood": round(self.human_state.mood, 3),
            },
        }

    def force_fire(self, impulse_type: ImpulseType) -> ImpulseEvent:
        payload = self._generate_payload(impulse_type)
        event = ImpulseEvent(
            id=str(uuid4()),
            impulse_type=impulse_type,
            payload=payload,
            state_snapshot=self.human_state.snapshot(),
            created_at=time.time(),
        )
        self._last_fire_time = time.time()
        self._next_fire_time = self._schedule_next()
        self.event_log.log(
            "impulse_forced", "impulse", {"type": impulse_type.value, "payload": payload}
        )
        return event
