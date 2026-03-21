from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional, Protocol

from humanclaw.core.config import HumanClawConfig
from humanclaw.core.models import TaskType


class Store(Protocol):
    def get(self, key: str) -> Optional[Dict[str, Any]]: ...
    def set(self, key: str, value: Dict[str, Any]) -> None: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


class HumanState:
    STORE_KEY = "human_state"

    def __init__(self, config: HumanClawConfig, store: Store, event_log: EventLog) -> None:
        self.config = config
        self.store = store
        self.event_log = event_log

        self.energy: float = 0.85
        self.mood: float = 0.0
        self.fatigue: float = 0.15
        self.boredom: float = 0.0
        self.social_load: float = 0.0
        self.focus: float = 0.5
        self._last_tick: float = time.time()
        self._idle: bool = True

        self.load()

    def tick(self) -> None:
        now = time.time()
        elapsed_hours = (now - self._last_tick) / 3600
        if elapsed_hours <= 0:
            return

        if self._idle:
            self.energy = min(1.0, self.energy + 0.03 * elapsed_hours)
            self.boredom = min(1.0, self.boredom + 0.08 * elapsed_hours)
            self.fatigue = max(0.0, self.fatigue - 0.04 * elapsed_hours)
            self.focus = max(0.0, self.focus - 0.04 * elapsed_hours)
        else:
            self.energy = max(0.0, self.energy - 0.02 * elapsed_hours)
            self.fatigue = min(1.0, self.fatigue + 0.01 * elapsed_hours)
            self.focus = max(0.0, self.focus - 0.02 * elapsed_hours)

        if self.mood > 0:
            self.mood = max(0.0, self.mood - 0.05 * elapsed_hours)
        elif self.mood < 0:
            self.mood = min(0.0, self.mood + 0.05 * elapsed_hours)

        self.social_load = max(0.0, self.social_load - 0.03 * elapsed_hours)

        self._clamp_all()
        self._last_tick = now
        self.save()

    def on_task_start(self) -> None:
        self._idle = False
        self.energy = max(0.0, self.energy - 0.03)
        self.boredom = max(0.0, self.boredom - 0.4)
        self.focus = min(1.0, self.focus + 0.15)
        self._clamp_all()
        self.event_log.log("task_start", "human_state", self.snapshot())
        self.save()

    def on_task_complete(self) -> None:
        self._idle = True
        self.energy = min(1.0, self.energy + 0.02)
        self.mood = min(1.0, self.mood + 0.05)
        self._clamp_all()
        self.event_log.log("task_complete", "human_state", self.snapshot())
        self.save()

    def on_interaction(self, sentiment: float) -> None:
        self.social_load = min(1.0, self.social_load + 0.1)
        self.mood = max(-1.0, min(1.0, self.mood + sentiment * 0.1))
        self._clamp_all()
        self.event_log.log("interaction", "human_state", {"sentiment": sentiment, **self.snapshot()})
        self.save()

    def on_positive_interaction(self) -> None:
        self.mood = min(1.0, self.mood + 0.1)
        self.energy = min(1.0, self.energy + 0.02)
        self.social_load = min(1.0, self.social_load + 0.08)
        self._clamp_all()
        self.event_log.log("positive_interaction", "human_state", self.snapshot())
        self.save()

    def on_negative_interaction(self) -> None:
        self.mood = max(-1.0, self.mood - 0.15)
        self.fatigue = min(1.0, self.fatigue + 0.05)
        self.social_load = min(1.0, self.social_load + 0.12)
        self._clamp_all()
        self.event_log.log("negative_interaction", "human_state", self.snapshot())
        self.save()

    def on_rest(self) -> None:
        self._idle = True
        self.energy = min(1.0, self.energy + 0.15)
        self.fatigue = max(0.0, self.fatigue - 0.2)
        self._clamp_all()
        self.event_log.log("rest", "human_state", self.snapshot())
        self.save()

    @property
    def decision_quality_multiplier(self) -> float:
        base = (self.energy * 0.5) + ((1 - self.fatigue) * 0.5)
        bonus = max(0.0, self.mood * 0.15)
        noise = random.gauss(0, 0.02)
        return max(0.1, min(1.0, base + bonus + noise))

    @property
    def preferred_task_type(self) -> TaskType:
        if self.mood > 0.3 and self.energy > 0.6:
            return TaskType.CREATIVE_OR_STRATEGIC
        if self.mood < -0.3 or self.fatigue > 0.6:
            return TaskType.MECHANICAL_OR_ROUTINE
        if self.mood < -0.1 and self.social_load > 0.5:
            return TaskType.SOLO_ANALYTICAL
        if self.social_load > 0.7:
            return TaskType.LOW_INTERACTION_FOCUSED
        return TaskType.ANY

    def snapshot(self) -> Dict[str, Any]:
        return {
            "energy": round(self.energy, 4),
            "mood": round(self.mood, 4),
            "fatigue": round(self.fatigue, 4),
            "boredom": round(self.boredom, 4),
            "social_load": round(self.social_load, 4),
            "focus": round(self.focus, 4),
        }

    def save(self) -> None:
        data = self.snapshot()
        data["_last_tick"] = self._last_tick
        data["_idle"] = self._idle
        self.store.set(self.STORE_KEY, data)

    def load(self) -> None:
        data = self.store.get(self.STORE_KEY)
        if data is None:
            return
        self.energy = data.get("energy", self.energy)
        self.mood = data.get("mood", self.mood)
        self.fatigue = data.get("fatigue", self.fatigue)
        self.boredom = data.get("boredom", self.boredom)
        self.social_load = data.get("social_load", self.social_load)
        self.focus = data.get("focus", self.focus)
        self._last_tick = data.get("_last_tick", self._last_tick)
        self._idle = data.get("_idle", self._idle)

    def _clamp_all(self) -> None:
        self.energy = max(0.0, min(1.0, self.energy))
        self.mood = max(-1.0, min(1.0, self.mood))
        self.fatigue = max(0.0, min(1.0, self.fatigue))
        self.boredom = max(0.0, min(1.0, self.boredom))
        self.social_load = max(0.0, min(1.0, self.social_load))
        self.focus = max(0.0, min(1.0, self.focus))
