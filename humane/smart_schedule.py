"""Smart Scheduling / Best-Time-To-Contact Engine.

Analyzes interaction timestamps and sentiment scores to determine
the optimal time to reach out to each entity.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from humane.core.store import Store


class SmartScheduler:

    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_response_patterns(self, entity_id: str) -> dict:
        """Analyze interaction timestamps to find optimal contact patterns.

        Returns a dict with:
            best_day_of_week        – day name with fastest/most-positive interactions
            best_hour               – hour of day (0-23) with most positive sentiment
            avg_response_time_hours – average gap between consecutive interactions
            interaction_frequency_days – average days between interactions
            last_contact_days_ago   – days since the most recent interaction
            suggested_next_contact  – ISO datetime of the next best window
        """
        entity = self.store.get_entity(entity_id)
        if entity is None:
            return {"error": f"Entity {entity_id} not found"}

        interactions = self.store.get_interactions(entity_id=entity_id, limit=500)
        if not interactions:
            return self._empty_analysis(entity)

        # Interactions come newest-first; reverse for chronological order.
        interactions = list(reversed(interactions))
        timestamps = [i["created_at"] for i in interactions]
        sentiments = [i["sentiment"] for i in interactions]

        # ---- best day of week (highest avg sentiment) ----
        day_sentiments: Dict[int, List[float]] = defaultdict(list)
        for ts, sent in zip(timestamps, sentiments):
            dow = datetime.fromtimestamp(ts).weekday()  # 0=Mon
            day_sentiments[dow].append(sent)

        best_day_idx = max(day_sentiments, key=lambda d: (
            sum(day_sentiments[d]) / len(day_sentiments[d])
        )) if day_sentiments else 0
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday"]
        best_day = day_names[best_day_idx]

        # ---- best hour (highest avg sentiment) ----
        hour_sentiments: Dict[int, List[float]] = defaultdict(list)
        for ts, sent in zip(timestamps, sentiments):
            hour = datetime.fromtimestamp(ts).hour
            hour_sentiments[hour].append(sent)

        best_hour = max(hour_sentiments, key=lambda h: (
            sum(hour_sentiments[h]) / len(hour_sentiments[h])
        )) if hour_sentiments else 10  # default 10am

        # ---- average response time (gap between consecutive interactions) ----
        gaps_hours: List[float] = []
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i - 1]) / 3600.0
            gaps_hours.append(gap)
        avg_response_time_hours = round(
            sum(gaps_hours) / len(gaps_hours), 2
        ) if gaps_hours else 0.0

        # ---- interaction frequency in days ----
        if len(timestamps) >= 2:
            span_days = (timestamps[-1] - timestamps[0]) / 86400.0
            interaction_frequency_days = round(
                span_days / (len(timestamps) - 1), 2
            )
        else:
            interaction_frequency_days = 0.0

        # ---- last contact ----
        last_ts = timestamps[-1]
        last_contact_days_ago = round(
            (time.time() - last_ts) / 86400.0, 1
        )

        # ---- suggested next contact ----
        suggested_next_contact = self._next_occurrence(
            best_day_idx, best_hour
        ).isoformat()

        return {
            "entity_id": entity_id,
            "entity_name": entity.name,
            "best_day_of_week": best_day,
            "best_hour": best_hour,
            "avg_response_time_hours": avg_response_time_hours,
            "interaction_frequency_days": interaction_frequency_days,
            "last_contact_days_ago": last_contact_days_ago,
            "suggested_next_contact": suggested_next_contact,
            "total_interactions": len(interactions),
        }

    def get_schedule_for_all(self) -> List[dict]:
        """Return schedule suggestions for every entity, sorted by urgency.

        Urgency is determined by how overdue the contact is relative to the
        entity's typical interaction frequency.
        """
        entities = self.store.list_entities()
        results: List[dict] = []

        for entity in entities:
            analysis = self.analyze_response_patterns(entity.entity_id)
            if "error" in analysis:
                continue

            # Compute urgency: how many days overdue vs expected frequency
            freq = analysis["interaction_frequency_days"]
            last = analysis["last_contact_days_ago"]

            if freq > 0:
                overdue_ratio = last / freq
            else:
                overdue_ratio = last / 7.0  # fallback: weekly cadence

            # Classify urgency
            if overdue_ratio >= 2.0:
                urgency = "overdue"
                reason = f"Haven't spoken in {int(last)} days"
            elif overdue_ratio >= 1.0:
                urgency = "due_soon"
                reason = f"Due for contact ({int(last)} days since last)"
            else:
                urgency = "scheduled"
                reason = "Best time based on patterns"

            analysis["urgency"] = urgency
            analysis["reason"] = reason
            analysis["overdue_ratio"] = round(overdue_ratio, 2)
            results.append(analysis)

        # Sort: overdue first (highest overdue_ratio), then due_soon, then scheduled
        urgency_order = {"overdue": 0, "due_soon": 1, "scheduled": 2}
        results.sort(key=lambda r: (urgency_order.get(r["urgency"], 3), -r["overdue_ratio"]))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _next_occurrence(target_weekday: int, target_hour: int) -> datetime:
        """Return the next future datetime matching the given weekday + hour."""
        now = datetime.now()
        days_ahead = target_weekday - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now.hour >= target_hour):
            days_ahead += 7
        candidate = now.replace(
            hour=target_hour, minute=0, second=0, microsecond=0
        ) + timedelta(days=days_ahead)
        return candidate

    @staticmethod
    def _empty_analysis(entity) -> dict:
        return {
            "entity_id": entity.entity_id,
            "entity_name": entity.name,
            "best_day_of_week": "N/A",
            "best_hour": 10,
            "avg_response_time_hours": 0.0,
            "interaction_frequency_days": 0.0,
            "last_contact_days_ago": round(
                (time.time() - entity.created_at) / 86400.0, 1
            ) if entity.created_at else 0.0,
            "suggested_next_contact": datetime.now().isoformat(),
            "total_interactions": 0,
        }
