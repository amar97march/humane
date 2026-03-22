"""Rate Limiter Plugin — blocks actions if too many of the same type were approved recently.

Copy this file to ~/.humane/plugins/ to activate it.

Configuration:
    Set max_per_hour on the class or override in a subclass.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List

from humane.core.models import GateResult, ProposedAction, Verdict
from humane.plugins import HumanePlugin


class RateLimiterPlugin(HumanePlugin):
    """Blocks actions if more than N actions of the same type were approved in the last hour.

    Attributes:
        max_per_hour: Maximum number of actions of the same type allowed per hour.
                      Defaults to 10.
    """

    name = "rate_limiter"
    version = "1.0.0"

    def __init__(self, max_per_hour: int = 10):
        self.max_per_hour = max_per_hour
        # Tracks timestamps of approved actions keyed by action_type
        self._action_log: Dict[str, List[float]] = defaultdict(list)
        self._conductor = None

    def on_load(self, conductor) -> None:
        self._conductor = conductor

    def on_unload(self) -> None:
        self._action_log.clear()
        self._conductor = None

    def evaluate(self, action: ProposedAction, context: dict) -> GateResult:
        """Check whether the action type has exceeded the rate limit."""
        now = time.time()
        one_hour_ago = now - 3600
        action_type = action.action_type

        # Prune old entries
        self._action_log[action_type] = [
            ts for ts in self._action_log[action_type] if ts > one_hour_ago
        ]

        recent_count = len(self._action_log[action_type])

        if recent_count >= self.max_per_hour:
            return GateResult(
                engine=f"plugin:{self.name}",
                verdict=Verdict.HOLD,
                score=1.0,
                reason=(
                    f"Rate limit exceeded: {recent_count}/{self.max_per_hour} "
                    f"'{action_type}' actions in the last hour"
                ),
                metadata={
                    "plugin": self.name,
                    "action_type": action_type,
                    "count": recent_count,
                    "max_per_hour": self.max_per_hour,
                },
            )

        # Record this action as approved (will be counted for future checks)
        self._action_log[action_type].append(now)

        return GateResult(
            engine=f"plugin:{self.name}",
            verdict=Verdict.PROCEED,
            score=recent_count / self.max_per_hour,
            reason=(
                f"Rate OK: {recent_count + 1}/{self.max_per_hour} "
                f"'{action_type}' actions in the last hour"
            ),
            metadata={
                "plugin": self.name,
                "action_type": action_type,
                "count": recent_count + 1,
                "max_per_hour": self.max_per_hour,
            },
        )
