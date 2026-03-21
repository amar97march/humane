"""Mood-Aware Task Sequencer — reorders task queue based on HumanState."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from humane.engines.human_state import HumanState

from humane.core.models import TaskType


class MoodAwareTaskSequencer:

    TASK_TYPE_AFFINITY = {
        TaskType.CREATIVE_OR_STRATEGIC: {"min_energy": 0.6, "min_mood": 0.1, "max_fatigue": 0.5},
        TaskType.MECHANICAL_OR_ROUTINE: {"min_energy": 0.0, "min_mood": -1.0, "max_fatigue": 1.0},
        TaskType.SOLO_ANALYTICAL: {"min_energy": 0.3, "min_mood": -0.5, "max_fatigue": 0.7},
        TaskType.LOW_INTERACTION_FOCUSED: {"min_energy": 0.2, "min_mood": -0.5, "max_fatigue": 0.8},
        TaskType.ANY: {"min_energy": 0.0, "min_mood": -1.0, "max_fatigue": 1.0},
    }

    def __init__(self, human_state: HumanState):
        self.human_state = human_state

    def reorder(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        preferred = self.human_state.preferred_task_type
        return sorted(tasks, key=lambda t: self._score_task(t, preferred), reverse=True)

    def _score_task(self, task: dict[str, Any], preferred: TaskType) -> float:
        task_type = task.get("task_type", TaskType.ANY)
        if isinstance(task_type, str):
            try:
                task_type = TaskType(task_type)
            except ValueError:
                task_type = TaskType.ANY

        score = 0.5
        if task_type == preferred:
            score += 1.0
        elif preferred == TaskType.ANY:
            score += 0.5

        affinity = self.TASK_TYPE_AFFINITY.get(task_type, self.TASK_TYPE_AFFINITY[TaskType.ANY])
        if self.human_state.energy >= affinity["min_energy"]:
            score += 0.2
        if self.human_state.mood >= affinity["min_mood"]:
            score += 0.2
        if self.human_state.fatigue <= affinity["max_fatigue"]:
            score += 0.2

        priority = task.get("priority", 0)
        score += priority * 0.1

        return score
