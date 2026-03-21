"""HumanClaw Conductor — orchestrates all 10 engines through the decision gate stack."""

from __future__ import annotations
import time
from typing import Optional
from uuid import uuid4

from humanclaw.core.models import (
    ProposedAction, Verdict, GateResult, EvaluationResult, HoldItem,
)
from humanclaw.core.config import HumanClawConfig
from humanclaw.core.store import Store
from humanclaw.core.events import EventLog
from humanclaw.engines.human_state import HumanState
from humanclaw.engines.inaction_guard import InactionGuard
from humanclaw.engines.impulse import StochasticImpulseEngine
from humanclaw.engines.relational import RelationalMemoryEngine
from humanclaw.engines.dissent import DissentEngine, ConvictionOverride
from humanclaw.engines.goal_abandon import GoalAbandonmentEngine
from humanclaw.engines.memory_decay import MemoryDecayEngine
from humanclaw.engines.social_risk import SocialRiskEngine
from humanclaw.engines.anomaly import SocialAnomalyDetector
from humanclaw.engines.values import ValuesBoundaryEngine
from humanclaw.sequencer import MoodAwareTaskSequencer


class Conductor:

    def __init__(self, config: Optional[HumanClawConfig] = None, db_path: Optional[str] = None):
        self.config = config or HumanClawConfig()
        _db = db_path or self.config.db_path
        self.store = Store(_db)
        self.store.initialize()
        self.event_log = EventLog(self.store)

        self.human_state = HumanState(self.config, self.store, self.event_log)
        self.inaction_guard = InactionGuard(self.config, self.human_state, self.store, self.event_log)
        self.impulse_engine = StochasticImpulseEngine(self.config, self.human_state, self.event_log)
        self.relational = RelationalMemoryEngine(self.config, self.store, self.event_log)
        self.dissent = DissentEngine(self.config, self.event_log)
        self.conviction = ConvictionOverride(self.event_log)
        self.goal_engine = GoalAbandonmentEngine(self.config, self.human_state, self.store, self.event_log)
        self.memory_decay = MemoryDecayEngine(self.config, self.store, self.event_log)
        self.social_risk = SocialRiskEngine(self.config, self.relational, self.event_log)
        self.anomaly_detector = SocialAnomalyDetector(self.config, self.relational, self.store, self.event_log)
        self.values = ValuesBoundaryEngine(self.config, self.store, self.event_log)
        self.sequencer = MoodAwareTaskSequencer(self.human_state)

    def evaluate(self, action: ProposedAction) -> EvaluationResult:
        """Run action through the full 10-step decision gate stack.

        Order (from spec):
        1. State tick
        2. Context assembly (relational + memory)
        3. Conviction Override check
        4. Values Boundary (Engine 10) — hard block first
        5. Social Risk (Engine 8)
        6. Dissent (Engine 5)
        7. InactionGuard (Engine 3)

        Returns EvaluationResult with final verdict and full audit trail.
        """
        audit: list[str] = []
        gate_results: list[GateResult] = []

        self.human_state.tick()
        audit.append(f"State tick: energy={self.human_state.energy:.2f} mood={self.human_state.mood:+.2f} fatigue={self.human_state.fatigue:.2f}")

        if action.target_entity:
            ctx = self.relational.get_context(action.target_entity)
            audit.append(f"Relational context loaded for {action.target_entity}: trust={ctx.get('trust_level', 'unknown')}")

        conviction_result = self.conviction.check(action)
        if conviction_result and conviction_result.verdict == Verdict.HOLD:
            gate_results.append(conviction_result)
            audit.append(f"CONVICTION OVERRIDE raised: {conviction_result.reason}")
            hold = self._create_hold(action, conviction_result, "conviction_override")
            return EvaluationResult(
                action=action, final_verdict=Verdict.HOLD,
                gate_results=gate_results, hold_item=hold, audit_trail=audit,
            )

        values_result = self.values.evaluate(action)
        gate_results.append(values_result)
        audit.append(f"Values Boundary: {values_result.reason}")
        if values_result.verdict == Verdict.HOLD:
            is_hard = values_result.metadata.get("unconditional_block", False)
            hold = self._create_hold(action, values_result, "values_boundary")
            if is_hard:
                audit.append("HARD VALUE VIOLATION — unconditional block, no override path")
            return EvaluationResult(
                action=action, final_verdict=Verdict.HOLD,
                gate_results=gate_results, hold_item=hold, audit_trail=audit,
            )

        social_result = self.social_risk.evaluate(action)
        gate_results.append(social_result)
        audit.append(f"Social Risk: score={social_result.score:.2f} — {social_result.reason}")
        if social_result.verdict == Verdict.HOLD:
            hold = self._create_hold(action, social_result, "social_risk")
            return EvaluationResult(
                action=action, final_verdict=Verdict.HOLD,
                gate_results=gate_results, hold_item=hold, audit_trail=audit,
            )

        dissent_result = self.dissent.evaluate(action)
        gate_results.append(dissent_result)
        audit.append(f"Dissent: score={dissent_result.score:.2f} — {dissent_result.reason}")
        if dissent_result.verdict == Verdict.HOLD:
            hold = self._create_hold(action, dissent_result, "dissent")
            return EvaluationResult(
                action=action, final_verdict=Verdict.HOLD,
                gate_results=gate_results, hold_item=hold, audit_trail=audit,
            )

        ig_result = self.inaction_guard.evaluate(action)
        gate_results.append(ig_result)
        audit.append(f"InactionGuard: adjusted_conf={ig_result.score:.2f} — {ig_result.reason}")

        if ig_result.verdict == Verdict.DEFER:
            hold = self._create_hold(action, ig_result, "inaction_guard")
            return EvaluationResult(
                action=action, final_verdict=Verdict.DEFER,
                gate_results=gate_results, hold_item=hold, audit_trail=audit,
            )

        if ig_result.verdict == Verdict.HOLD:
            hold = self._create_hold(action, ig_result, "inaction_guard")
            return EvaluationResult(
                action=action, final_verdict=Verdict.HOLD,
                gate_results=gate_results, hold_item=hold, audit_trail=audit,
            )

        audit.append("ALL GATES PASSED — action PROCEED")
        self.event_log.log("action_proceed", "conductor", {
            "action_type": action.action_type,
            "confidence": action.confidence,
        })

        self.human_state.on_task_complete()

        return EvaluationResult(
            action=action, final_verdict=Verdict.PROCEED,
            gate_results=gate_results, hold_item=None, audit_trail=audit,
        )

    def _create_hold(self, action: ProposedAction, gate_result: GateResult, source: str) -> HoldItem:
        hold = HoldItem(
            id=str(uuid4()),
            action=action,
            adjusted_confidence=gate_result.score,
            hold_reason=gate_result.reason,
            hold_source=source,
            verdict=gate_result.verdict,
            created_at=time.time(),
            expires_at=time.time() + 86400,
        )
        self.store.add_hold_item(hold)
        self.event_log.log("action_held", source, {
            "hold_id": hold.id,
            "action_type": action.action_type,
            "reason": gate_result.reason,
        })
        return hold

    def tick(self):
        """Periodic tick — update state, check impulses, decay memory."""
        self.human_state.tick()
        self.memory_decay.decay_tick()

        impulse = self.impulse_engine.check_and_fire()
        if impulse:
            action = ProposedAction(
                action_type=f"impulse_{impulse.impulse_type.value}",
                payload=impulse.payload,
                confidence=0.6,
                rationale=f"Internally driven {impulse.impulse_type.value} impulse",
                source="impulse",
            )
            return self.evaluate(action)
        return None

    def approve_hold(self, hold_id: str):
        self.inaction_guard.approve(hold_id)

    def reject_hold(self, hold_id: str):
        self.inaction_guard.reject(hold_id)

    def get_hold_queue(self) -> list[HoldItem]:
        return self.store.get_hold_queue()

    def get_state_snapshot(self) -> dict:
        return self.human_state.snapshot()
