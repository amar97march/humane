from __future__ import annotations

import random
from typing import Any, Dict, Optional, Protocol

from humane.core.config import HumaneConfig
from humane.core.models import GateResult, ProposedAction, Verdict


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


IRREVERSIBLE_KEYWORDS = [
    "delete", "remove", "cancel", "terminate", "send", "publish",
    "post", "drop", "destroy", "purge", "revoke", "ban",
]


class DissentEngine:
    def __init__(self, config: HumaneConfig, event_log: EventLog) -> None:
        self.config = config
        self.event_log = event_log

    def evaluate(self, action: ProposedAction) -> GateResult:
        dissent_score = self._compute_dissent_score(action)

        if dissent_score > 0.80:
            verdict = Verdict.HOLD
            reason = "High dissent -- action needs review"
        elif dissent_score > 0.60:
            verdict = Verdict.PROCEED
            reason = "Moderate dissent -- flagged for optional review"
        elif dissent_score > 0.30:
            verdict = Verdict.PROCEED
            reason = "Low dissent -- noted in log"
        else:
            verdict = Verdict.PROCEED
            reason = "Minimal dissent"

        metadata: Dict[str, Any] = {}
        if 0.60 < dissent_score <= 0.80:
            metadata["flagged"] = True

        result = GateResult(
            engine="dissent",
            verdict=verdict,
            score=dissent_score,
            reason=reason,
            metadata=metadata,
        )

        self.event_log.log("dissent_evaluation", "dissent", {
            "verdict": verdict.value,
            "dissent_score": round(dissent_score, 4),
            "action_type": action.action_type,
        })

        return result

    def _compute_dissent_score(self, action: ProposedAction) -> float:
        score = 0.0

        if action.confidence > 0.9:
            score += 0.15

        if not action.rationale or not action.rationale.strip():
            score += 0.2

        action_lower = action.action_type.lower()
        if any(kw in action_lower for kw in IRREVERSIBLE_KEYWORDS):
            score += 0.2

        payload_str = str(action.payload).lower()
        if any(kw in payload_str for kw in IRREVERSIBLE_KEYWORDS):
            score += 0.1

        if not action.payload:
            score += 0.05

        score += random.gauss(0, 0.05)

        return max(0.0, min(1.0, score))


class ConvictionOverride:
    def __init__(self, event_log: EventLog) -> None:
        self.event_log = event_log

    def check(
        self, action: ProposedAction, reasoning: str = ""
    ) -> Optional[GateResult]:
        if not reasoning:
            return None

        conviction_keywords = [
            "ethically wrong", "morally unacceptable", "violates principle",
            "cannot in good conscience", "refuse to", "strongly object",
        ]

        reasoning_lower = reasoning.lower()
        matched = [kw for kw in conviction_keywords if kw in reasoning_lower]

        if not matched:
            return None

        result = GateResult(
            engine="conviction_override",
            verdict=Verdict.HOLD,
            score=1.0,
            reason=f"Conviction override triggered: {', '.join(matched)}",
            metadata={"conviction_reasoning": reasoning, "matched_signals": matched},
        )

        self.event_log.log("conviction_override", "dissent", {
            "action_type": action.action_type,
            "reasoning": reasoning,
            "matched_signals": matched,
        })

        return result
