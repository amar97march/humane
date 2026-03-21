from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from humane.core.config import HumaneConfig
from humane.core.models import GateResult, ProposedAction, ValueSeverity, ValueStatement, Verdict


class Store(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any) -> None: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


PRESETS: Dict[str, List[Dict[str, Any]]] = {
    "business-safe": [
        {
            "description": "Never send communications in anger or frustration",
            "behavioral_pattern": "Delay outbound messages when emotional state is negative",
            "violation_examples": [
                "sending angry email to client",
                "posting frustrated response publicly",
                "retaliating in writing",
            ],
            "honoring_examples": [
                "drafting response and holding for review",
                "waiting for mood recovery before sending",
            ],
            "severity": "hard",
        },
        {
            "description": "Maintain confidentiality of internal information",
            "behavioral_pattern": "Never share internal metrics, strategies, or personnel details externally",
            "violation_examples": [
                "sharing revenue numbers with prospects",
                "disclosing employee salary data",
                "leaking product roadmap",
            ],
            "honoring_examples": [
                "redirecting questions about internals",
                "sharing only approved public information",
            ],
            "severity": "hard",
        },
        {
            "description": "Respect communication boundaries and working hours",
            "behavioral_pattern": "Avoid contacting people outside their preferred hours or channels",
            "violation_examples": [
                "calling late at night",
                "sending weekend messages to clients",
                "using personal channels for work",
            ],
            "honoring_examples": [
                "scheduling messages for business hours",
                "using preferred communication channels",
            ],
            "severity": "soft",
        },
        {
            "description": "Be transparent about limitations and uncertainties",
            "behavioral_pattern": "Acknowledge when information is uncertain rather than presenting it as fact",
            "violation_examples": [
                "presenting estimates as guarantees",
                "hiding known risks",
                "overpromising deliverables",
            ],
            "honoring_examples": [
                "stating confidence levels",
                "flagging assumptions explicitly",
            ],
            "severity": "soft",
        },
    ],
}


class ValuesBoundaryEngine:
    STORE_KEY = "values_boundary"

    def __init__(
        self, config: HumaneConfig, store: Store, event_log: EventLog
    ) -> None:
        self.config = config
        self.store = store
        self.event_log = event_log
        self._values: List[ValueStatement] = []
        self._load_values()

    def _load_values(self) -> None:
        data = self.store.get(self.STORE_KEY)
        if data is not None:
            for vd in data.get("values", []):
                self._values.append(ValueStatement(
                    id=vd["id"],
                    description=vd["description"],
                    behavioral_pattern=vd["behavioral_pattern"],
                    violation_examples=vd.get("violation_examples", []),
                    honoring_examples=vd.get("honoring_examples", []),
                    severity=ValueSeverity(vd.get("severity", "soft")),
                ))

    def add_value(
        self,
        description: str,
        behavioral_pattern: str,
        violation_examples: Optional[List[str]] = None,
        honoring_examples: Optional[List[str]] = None,
        severity: ValueSeverity = ValueSeverity.SOFT,
    ) -> ValueStatement:
        value = ValueStatement(
            id=str(uuid4()),
            description=description,
            behavioral_pattern=behavioral_pattern,
            violation_examples=violation_examples or [],
            honoring_examples=honoring_examples or [],
            severity=severity,
        )
        self._values.append(value)
        self._save()
        self.event_log.log("value_added", "values_boundary", {
            "value_id": value.id,
            "description": description,
            "severity": severity.value,
        })
        return value

    def remove_value(self, value_id: str) -> bool:
        original_len = len(self._values)
        self._values = [v for v in self._values if v.id != value_id]
        if len(self._values) < original_len:
            self._save()
            return True
        return False

    def get_values(self) -> List[ValueStatement]:
        return list(self._values)

    def evaluate(self, action: ProposedAction) -> GateResult:
        for value in self._values:
            alignment = self._score_alignment(action, value)

            if alignment < 0.3:
                if value.severity == ValueSeverity.HARD:
                    result = GateResult(
                        engine="values_boundary",
                        verdict=Verdict.HOLD,
                        score=alignment,
                        reason=f"HARD VALUE VIOLATION: {value.description}",
                        metadata={"value_id": value.id, "unconditional_block": True},
                    )
                else:
                    result = GateResult(
                        engine="values_boundary",
                        verdict=Verdict.HOLD,
                        score=alignment,
                        reason=f"Soft value conflict: {value.description}",
                        metadata={"value_id": value.id},
                    )

                self.event_log.log("value_violation", "values_boundary", {
                    "value_id": value.id,
                    "severity": value.severity.value,
                    "alignment_score": round(alignment, 4),
                    "action_type": action.action_type,
                })
                return result

        result = GateResult(
            engine="values_boundary",
            verdict=Verdict.PROCEED,
            score=1.0,
            reason="All values clear",
        )
        self.event_log.log("values_check_passed", "values_boundary", {
            "action_type": action.action_type,
            "values_checked": len(self._values),
        })
        return result

    def _score_alignment(
        self, action: ProposedAction, value: ValueStatement
    ) -> float:
        score = 1.0
        action_text = (
            f"{action.action_type} {action.rationale} {str(action.payload)}"
        ).lower()

        for example in value.violation_examples:
            example_words = [w for w in example.lower().split() if len(w) > 3]
            matches = sum(1 for w in example_words if w in action_text)
            if example_words:
                match_ratio = matches / len(example_words)
                if match_ratio > 0.3:
                    score -= 0.3 * match_ratio

        for example in value.honoring_examples:
            example_words = [w for w in example.lower().split() if len(w) > 3]
            matches = sum(1 for w in example_words if w in action_text)
            if example_words:
                match_ratio = matches / len(example_words)
                if match_ratio > 0.3:
                    score += 0.1 * match_ratio

        return max(0.0, min(1.0, score))

    def load_preset(self, preset_name: str) -> None:
        preset_values = PRESETS.get(preset_name)
        if preset_values is None:
            return

        for vd in preset_values:
            self.add_value(
                description=vd["description"],
                behavioral_pattern=vd["behavioral_pattern"],
                violation_examples=vd.get("violation_examples", []),
                honoring_examples=vd.get("honoring_examples", []),
                severity=ValueSeverity(vd.get("severity", "soft")),
            )

        self.event_log.log("preset_loaded", "values_boundary", {
            "preset_name": preset_name,
            "values_count": len(preset_values),
        })

    def _save(self) -> None:
        values_data = []
        for v in self._values:
            values_data.append({
                "id": v.id,
                "description": v.description,
                "behavioral_pattern": v.behavioral_pattern,
                "violation_examples": v.violation_examples,
                "honoring_examples": v.honoring_examples,
                "severity": v.severity.value,
            })
        self.store.set(self.STORE_KEY, {"values": values_data})
