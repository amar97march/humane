from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from humanclaw.core.config import HumanClawConfig
from humanclaw.core.models import Goal


class HumanStateProtocol(Protocol):
    mood: float
    fatigue: float
    energy: float


class Store(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any) -> None: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


class GoalAbandonmentEngine:
    STORE_KEY = "goal_abandonment"

    def __init__(
        self,
        config: HumanClawConfig,
        human_state: HumanStateProtocol,
        store: Store,
        event_log: EventLog,
    ) -> None:
        self.config = config
        self.human_state = human_state
        self.store = store
        self.event_log = event_log
        self._goals: Dict[str, Goal] = {}
        self._load()

    def register_goal(
        self,
        description: str,
        expected_value: float = 1.0,
        milestones_total: int = 0,
    ) -> Goal:
        goal_id = str(uuid4())
        goal = Goal(
            id=goal_id,
            description=description,
            expected_value=expected_value,
            milestones_total=milestones_total,
            remaining_effort=1.0,
            progress_velocity=0.0,
            relevance_decay=1.0,
            created_at=time.time(),
            status="active",
        )
        self._goals[goal_id] = goal
        self._save()
        self.event_log.log("goal_registered", "goal_abandon", {
            "goal_id": goal_id,
            "description": description,
            "expected_value": expected_value,
        })
        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        return self._goals.get(goal_id)

    def active_goals(self) -> List[Goal]:
        return [g for g in self._goals.values() if g.status == "active"]

    def update_progress(
        self,
        goal_id: str,
        milestones_completed: Optional[int] = None,
        velocity: Optional[float] = None,
    ) -> None:
        goal = self._goals.get(goal_id)
        if goal is None or goal.status != "active":
            return

        if milestones_completed is not None:
            goal.milestones_completed = milestones_completed
            if goal.milestones_total > 0:
                progress_ratio = goal.milestones_completed / goal.milestones_total
                goal.remaining_effort = max(0.05, 1.0 - progress_ratio)

        if velocity is not None:
            goal.progress_velocity = velocity

        days_alive = max(1.0, (time.time() - goal.created_at) / 86400)
        goal.relevance_decay = max(0.1, 1.0 - (days_alive / 365.0) * 0.5)

        goal.last_evaluated_at = time.time()
        self._save()

        self.event_log.log("goal_progress_updated", "goal_abandon", {
            "goal_id": goal_id,
            "milestones_completed": goal.milestones_completed,
            "remaining_effort": goal.remaining_effort,
            "velocity": goal.progress_velocity,
            "relevance_decay": goal.relevance_decay,
        })

    def compute_roi(self, goal: Goal) -> float:
        effective_effort = max(0.1, goal.remaining_effort)
        raw_roi = (
            goal.progress_velocity * goal.relevance_decay * (goal.expected_value / effective_effort)
        )

        state_mod = 1.0
        if self.human_state.mood < -0.2 and self.human_state.fatigue > 0.5:
            state_mod = 0.7
        elif self.human_state.mood < -0.1 or self.human_state.fatigue > 0.4:
            state_mod = 0.85
        elif self.human_state.mood > 0.3 and self.human_state.energy > 0.6:
            state_mod = 1.15

        return raw_roi * state_mod

    def evaluate_goals(self) -> List[Dict[str, Any]]:
        proposals: List[Dict[str, Any]] = []

        for goal in self._goals.values():
            if goal.status != "active":
                continue

            roi = self.compute_roi(goal)
            goal.last_evaluated_at = time.time()

            if roi < self.config.goal_abandon_roi_threshold:
                proposal = {
                    "goal_id": goal.id,
                    "description": goal.description,
                    "roi": round(roi, 4),
                    "recommendation": "abandon" if roi < self.config.goal_abandon_roi_threshold * 0.5 else "pause",
                    "remaining_effort": round(goal.remaining_effort, 3),
                    "velocity": round(goal.progress_velocity, 3),
                    "relevance_decay": round(goal.relevance_decay, 3),
                }
                proposals.append(proposal)
                self.event_log.log("goal_abandon_proposal", "goal_abandon", proposal)

        self._save()
        return proposals

    def abandon(self, goal_id: str) -> None:
        goal = self._goals.get(goal_id)
        if goal is None:
            return
        goal.status = "abandoned"
        goal.last_evaluated_at = time.time()
        self._save()
        self.event_log.log("goal_abandoned", "goal_abandon", {
            "goal_id": goal_id,
            "description": goal.description,
        })

    def pause(self, goal_id: str, resume_days: int = 7) -> None:
        goal = self._goals.get(goal_id)
        if goal is None:
            return
        goal.status = "paused"
        goal.last_evaluated_at = time.time()
        self._save()
        self.event_log.log("goal_paused", "goal_abandon", {
            "goal_id": goal_id,
            "resume_days": resume_days,
        })

    def resume(self, goal_id: str) -> None:
        goal = self._goals.get(goal_id)
        if goal is None:
            return
        goal.status = "active"
        goal.last_evaluated_at = time.time()
        self._save()
        self.event_log.log("goal_resumed", "goal_abandon", {"goal_id": goal_id})

    def _save(self) -> None:
        goals_data: Dict[str, Dict[str, Any]] = {}
        for gid, g in self._goals.items():
            goals_data[gid] = {
                "id": g.id,
                "description": g.description,
                "expected_value": g.expected_value,
                "remaining_effort": g.remaining_effort,
                "progress_velocity": g.progress_velocity,
                "relevance_decay": g.relevance_decay,
                "milestones_total": g.milestones_total,
                "milestones_completed": g.milestones_completed,
                "created_at": g.created_at,
                "last_evaluated_at": g.last_evaluated_at,
                "status": g.status,
            }
        self.store.set(self.STORE_KEY, {"goals": goals_data})

    def _load(self) -> None:
        data = self.store.get(self.STORE_KEY)
        if data is None:
            return
        for gid, gd in data.get("goals", {}).items():
            self._goals[gid] = Goal(
                id=gd["id"],
                description=gd["description"],
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
