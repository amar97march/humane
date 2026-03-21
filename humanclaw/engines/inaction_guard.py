from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from humanclaw.core.config import HumanClawConfig
from humanclaw.core.models import GateResult, HoldItem, ProposedAction, Verdict


class HumanStateProtocol(Protocol):
    fatigue: float
    @property
    def decision_quality_multiplier(self) -> float: ...


class Store(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any) -> None: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


class InactionGuard:
    STORE_KEY = "inaction_guard"

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
        self._hold_queue: Dict[str, HoldItem] = {}
        self._calibration_data: List[Dict[str, Any]] = []
        self._load()

    def evaluate(self, action: ProposedAction) -> GateResult:
        dqm = self.human_state.decision_quality_multiplier
        adjusted = action.confidence * dqm

        if self.human_state.fatigue > self.config.fatigue_defer_threshold:
            result = GateResult(
                engine="inaction_guard",
                verdict=Verdict.DEFER,
                score=adjusted,
                reason=f"Fatigue {self.human_state.fatigue:.2f} above defer threshold",
            )
            self.event_log.log("gate_evaluation", "inaction_guard", {
                "verdict": result.verdict.value,
                "adjusted_confidence": adjusted,
                "dqm": dqm,
                "fatigue": self.human_state.fatigue,
            })
            return result

        if adjusted >= self.config.confidence_threshold:
            result = GateResult(
                engine="inaction_guard",
                verdict=Verdict.PROCEED,
                score=adjusted,
                reason=f"Adjusted confidence {adjusted:.2f} >= {self.config.confidence_threshold}",
            )
        else:
            result = GateResult(
                engine="inaction_guard",
                verdict=Verdict.HOLD,
                score=adjusted,
                reason=f"Adjusted confidence {adjusted:.2f} < {self.config.confidence_threshold}",
            )

        self.event_log.log("gate_evaluation", "inaction_guard", {
            "verdict": result.verdict.value,
            "adjusted_confidence": adjusted,
            "dqm": dqm,
            "raw_confidence": action.confidence,
        })
        return result

    def create_hold_item(
        self, action: ProposedAction, gate_result: GateResult, hold_source: str
    ) -> HoldItem:
        hold = HoldItem(
            id=str(uuid4()),
            action=action,
            adjusted_confidence=gate_result.score,
            hold_reason=gate_result.reason,
            hold_source=hold_source,
            verdict=gate_result.verdict,
            created_at=time.time(),
        )
        self._hold_queue[hold.id] = hold
        self._save()
        self.event_log.log("hold_created", "inaction_guard", {
            "hold_id": hold.id,
            "action_type": action.action_type,
            "source": hold_source,
            "reason": gate_result.reason,
        })
        return hold

    def get_hold_item(self, hold_id: str) -> Optional[HoldItem]:
        return self._hold_queue.get(hold_id)

    def pending_holds(self) -> List[HoldItem]:
        return [h for h in self._hold_queue.values() if not h.resolved]

    def approve(self, hold_id: str) -> None:
        hold = self._hold_queue.get(hold_id)
        if hold is None:
            return
        hold.resolved = True
        hold.resolution = "approved"
        self._calibration_data.append({
            "hold_id": hold_id,
            "resolution": "approved",
            "adjusted_confidence": hold.adjusted_confidence,
            "timestamp": time.time(),
        })
        self._save()
        self.event_log.log("hold_approved", "inaction_guard", {"hold_id": hold_id})

    def reject(self, hold_id: str) -> None:
        hold = self._hold_queue.get(hold_id)
        if hold is None:
            return
        hold.resolved = True
        hold.resolution = "rejected"
        self._calibration_data.append({
            "hold_id": hold_id,
            "resolution": "rejected",
            "adjusted_confidence": hold.adjusted_confidence,
            "timestamp": time.time(),
        })
        self._save()
        self.event_log.log("hold_rejected", "inaction_guard", {"hold_id": hold_id})

    def modify(self, hold_id: str, modified_action: ProposedAction) -> None:
        hold = self._hold_queue.get(hold_id)
        if hold is None:
            return
        hold.action = modified_action
        hold.resolved = True
        hold.resolution = "modified"
        self._calibration_data.append({
            "hold_id": hold_id,
            "resolution": "modified",
            "adjusted_confidence": hold.adjusted_confidence,
            "timestamp": time.time(),
        })
        self._save()
        self.event_log.log("hold_modified", "inaction_guard", {"hold_id": hold_id})

    def calibration_stats(self) -> Dict[str, Any]:
        total = len(self._calibration_data)
        if total == 0:
            return {"total": 0, "approved": 0, "rejected": 0, "modified": 0, "rates": {}}

        approved = sum(1 for d in self._calibration_data if d["resolution"] == "approved")
        rejected = sum(1 for d in self._calibration_data if d["resolution"] == "rejected")
        modified = sum(1 for d in self._calibration_data if d["resolution"] == "modified")

        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "modified": modified,
            "rates": {
                "approve_rate": approved / total,
                "reject_rate": rejected / total,
                "modify_rate": modified / total,
            },
        }

    def _save(self) -> None:
        self.store.set(self.STORE_KEY, {
            "calibration_data": self._calibration_data,
        })

    def _load(self) -> None:
        data = self.store.get(self.STORE_KEY)
        if data is not None:
            self._calibration_data = data.get("calibration_data", [])
