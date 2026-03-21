from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Protocol

from humane.core.config import HumaneConfig
from humane.core.models import EntityState, GateResult, Verdict


class RelationalEngine(Protocol):
    def get_entity(self, entity_id: str) -> Optional[EntityState]: ...


class Store(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any) -> None: ...


class EventLog(Protocol):
    def log(self, event_type: str, engine: str, data: Dict[str, Any]) -> None: ...


class SocialAnomalyDetector:
    STORE_KEY = "social_anomaly"
    MIN_INTERACTIONS_FOR_BASELINE = 5

    SIGNAL_WEIGHTS: Dict[str, float] = {
        "response_time_deviation": 0.25,
        "tone_shift": 0.25,
        "message_length_anomaly": 0.15,
        "expected_followup_absence": 0.15,
        "vocabulary_formality_shift": 0.10,
        "sentiment_trend": 0.10,
    }

    def __init__(
        self,
        config: HumaneConfig,
        relational_engine: RelationalEngine,
        store: Store,
        event_log: EventLog,
    ) -> None:
        self.config = config
        self.relational = relational_engine
        self.store = store
        self.event_log = event_log
        self._baselines: Dict[str, Dict[str, Any]] = {}
        self._load()

    def evaluate(self, entity_id: str, incoming_signal: Dict[str, Any]) -> GateResult:
        entity = self.relational.get_entity(entity_id)

        if entity is None or entity.interaction_count < self.MIN_INTERACTIONS_FOR_BASELINE:
            self._update_baseline(entity_id, incoming_signal)
            return GateResult(
                engine="anomaly_detector",
                verdict=Verdict.PROCEED,
                score=0.0,
                reason="Learning mode -- baseline building",
            )

        anomaly_score = self._compute_anomaly_score(entity_id, incoming_signal)
        self._update_baseline(entity_id, incoming_signal)

        if anomaly_score > self.config.anomaly_hard_threshold:
            result = GateResult(
                engine="anomaly_detector",
                verdict=Verdict.HOLD,
                score=anomaly_score,
                reason="Hard anomaly flag -- significant behavior change detected",
            )
        elif anomaly_score > self.config.anomaly_soft_threshold:
            result = GateResult(
                engine="anomaly_detector",
                verdict=Verdict.PROCEED,
                score=anomaly_score,
                reason="Soft anomaly flag -- response pattern deviation detected",
                metadata={
                    "context_note": (
                        "Response pattern deviation detected for entity. "
                        "Consider tone and timing carefully."
                    )
                },
            )
        else:
            result = GateResult(
                engine="anomaly_detector",
                verdict=Verdict.PROCEED,
                score=anomaly_score,
                reason="No anomaly detected",
            )

        self.event_log.log("anomaly_evaluation", "anomaly_detector", {
            "entity_id": entity_id,
            "anomaly_score": round(anomaly_score, 4),
            "verdict": result.verdict.value,
        })

        self._save()
        return result

    def _compute_anomaly_score(
        self, entity_id: str, signal: Dict[str, Any]
    ) -> float:
        baseline = self._baselines.get(entity_id, {})
        score = 0.0

        if "response_time" in signal and "avg_response_time" in baseline:
            avg = baseline["avg_response_time"]
            if avg > 0:
                deviation = abs(signal["response_time"] - avg) / max(avg, 1.0)
                score += self.SIGNAL_WEIGHTS["response_time_deviation"] * min(1.0, deviation)

        if "sentiment" in signal and "avg_sentiment" in baseline:
            shift = abs(signal["sentiment"] - baseline["avg_sentiment"])
            score += self.SIGNAL_WEIGHTS["tone_shift"] * min(1.0, shift * 2)

        if "message_length" in signal and "avg_length" in baseline and "std_length" in baseline:
            std = baseline["std_length"]
            if std > 0:
                z = abs(signal["message_length"] - baseline["avg_length"]) / std
                if z > 2:
                    score += self.SIGNAL_WEIGHTS["message_length_anomaly"] * min(1.0, z / 4)

        if "expected_followup" in signal and signal["expected_followup"] is False:
            score += self.SIGNAL_WEIGHTS["expected_followup_absence"] * 0.7

        if "formality" in signal and "avg_formality" in baseline:
            formality_shift = abs(signal["formality"] - baseline["avg_formality"])
            score += self.SIGNAL_WEIGHTS["vocabulary_formality_shift"] * min(1.0, formality_shift * 2)

        if "recent_sentiments" in baseline:
            recent = baseline["recent_sentiments"][-3:]
            if len(recent) >= 3 and all(s < 0 for s in recent):
                score += self.SIGNAL_WEIGHTS["sentiment_trend"] * 0.8

        return max(0.0, min(1.0, score))

    def _update_baseline(self, entity_id: str, signal: Dict[str, Any]) -> None:
        if entity_id not in self._baselines:
            self._baselines[entity_id] = {
                "sample_count": 0,
                "avg_response_time": 0.0,
                "avg_sentiment": 0.0,
                "avg_length": 0.0,
                "std_length": 0.0,
                "avg_formality": 0.5,
                "recent_sentiments": [],
                "_lengths": [],
            }

        b = self._baselines[entity_id]
        n = b["sample_count"]
        new_n = n + 1
        b["sample_count"] = new_n

        if "response_time" in signal:
            b["avg_response_time"] = (
                (b["avg_response_time"] * n + signal["response_time"]) / new_n
            )

        if "sentiment" in signal:
            b["avg_sentiment"] = (
                (b["avg_sentiment"] * n + signal["sentiment"]) / new_n
            )
            b["recent_sentiments"].append(signal["sentiment"])
            if len(b["recent_sentiments"]) > 10:
                b["recent_sentiments"] = b["recent_sentiments"][-10:]

        if "message_length" in signal:
            b["_lengths"].append(signal["message_length"])
            if len(b["_lengths"]) > 50:
                b["_lengths"] = b["_lengths"][-50:]
            lengths = b["_lengths"]
            b["avg_length"] = sum(lengths) / len(lengths)
            if len(lengths) > 1:
                variance = sum((x - b["avg_length"]) ** 2 for x in lengths) / (len(lengths) - 1)
                b["std_length"] = math.sqrt(variance)

        if "formality" in signal:
            b["avg_formality"] = (
                (b["avg_formality"] * n + signal["formality"]) / new_n
            )

        self._save()

    def get_baseline(self, entity_id: str) -> Dict[str, Any]:
        baseline = self._baselines.get(entity_id, {})
        return {k: v for k, v in baseline.items() if not k.startswith("_")}

    def _save(self) -> None:
        self.store.set(self.STORE_KEY, {"baselines": self._baselines})

    def _load(self) -> None:
        data = self.store.get(self.STORE_KEY)
        if data is not None:
            self._baselines = data.get("baselines", {})
