"""Predictive Insights Engine — surfaces actionable insights from conductor engine data."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


# Trust level ordering for threshold detection
TRUST_LEVEL_ORDER = ["untrusted", "cautious", "neutral", "trusted", "deep_trust"]

# Thresholds
SENTIMENT_DECLINE_THRESHOLD = 0.2
SENTIMENT_DECLINE_WINDOW_DAYS = 7
GOAL_STALL_DAYS = 5
SOCIAL_LOAD_WARNING = 0.8
FATIGUE_WARNING = 0.7
BOREDOM_OPPORTUNITY = 0.6
COMMUNICATION_GAP_MULTIPLIER = 2.0
MIN_INTERACTIONS_FOR_GAP = 3


class PredictiveInsights:
    """Generates predictive insights from the conductor's engine data.

    Each insight is a dict with keys:
        type, severity, title, description, entity_id (optional), action_suggestion
    """

    def __init__(self, conductor: Any) -> None:
        self.conductor = conductor

    def generate_insights(self) -> List[Dict[str, Any]]:
        """Analyse all engine data and return a list of insight dicts."""
        insights: List[Dict[str, Any]] = []

        insights.extend(self._check_sentiment_decline())
        insights.extend(self._check_relationship_at_risk())
        insights.extend(self._check_goal_stalling())
        insights.extend(self._check_communication_gap())
        insights.extend(self._check_overload_warning())
        insights.extend(self._check_boredom_opportunity())
        insights.extend(self._check_trust_milestone())
        insights.extend(self._check_pattern_anomaly())

        # Sort by severity: critical first, then warning, then info
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        insights.sort(key=lambda i: severity_order.get(i["severity"], 3))

        return insights

    # ------------------------------------------------------------------
    # a. Sentiment decline
    # ------------------------------------------------------------------
    def _check_sentiment_decline(self) -> List[Dict[str, Any]]:
        insights = []
        now = time.time()
        window = SENTIMENT_DECLINE_WINDOW_DAYS * 86400
        relational = self.conductor.relational

        for entity in relational.list_entities():
            interactions = relational._interaction_log.get(entity.entity_id, [])
            if len(interactions) < 2:
                continue

            # Get interactions within the window
            recent = [i for i in interactions if now - i.get("timestamp", 0) <= window]
            older = [i for i in interactions if now - i.get("timestamp", 0) > window]

            if not recent or not older:
                # Try splitting recent interactions into halves
                if len(interactions) >= 4:
                    mid = len(interactions) // 2
                    older_half = interactions[:mid]
                    recent_half = interactions[mid:]
                    avg_old = sum(i.get("sentiment", 0) for i in older_half) / len(older_half)
                    avg_recent = sum(i.get("sentiment", 0) for i in recent_half) / len(recent_half)
                    decline = avg_old - avg_recent
                else:
                    continue
            else:
                avg_old = sum(i.get("sentiment", 0) for i in older) / len(older)
                avg_recent = sum(i.get("sentiment", 0) for i in recent) / len(recent)
                decline = avg_old - avg_recent

            if decline > SENTIMENT_DECLINE_THRESHOLD:
                severity = "critical" if decline > 0.5 else "warning"
                insights.append({
                    "type": "sentiment_decline",
                    "severity": severity,
                    "title": f"Sentiment declining for {entity.name}",
                    "description": (
                        f"Sentiment has dropped by {decline:.2f} "
                        f"(from {avg_old:.2f} to {avg_recent:.2f}). "
                        f"This may indicate a deteriorating relationship."
                    ),
                    "entity_id": entity.entity_id,
                    "action_suggestion": (
                        "Consider reaching out with a positive interaction "
                        "or addressing any recent issues."
                    ),
                })
        return insights

    # ------------------------------------------------------------------
    # b. Relationship at risk
    # ------------------------------------------------------------------
    def _check_relationship_at_risk(self) -> List[Dict[str, Any]]:
        insights = []
        relational = self.conductor.relational

        for entity in relational.list_entities():
            health = entity.relationship_health.value
            if health not in ("fragile", "strained"):
                continue

            # Check if sentiment is also declining
            interactions = relational._interaction_log.get(entity.entity_id, [])
            declining = False
            if len(interactions) >= 3:
                recent_3 = interactions[-3:]
                sentiments = [i.get("sentiment", 0) for i in recent_3]
                if all(s < 0 for s in sentiments) or (len(sentiments) >= 2 and sentiments[-1] < sentiments[0]):
                    declining = True

            severity = "critical" if health == "strained" else "warning"
            if declining:
                severity = "critical"

            insights.append({
                "type": "relationship_at_risk",
                "severity": severity,
                "title": f"Relationship at risk: {entity.name}",
                "description": (
                    f"Relationship health is '{health}' "
                    f"(sentiment: {entity.sentiment_score:.2f}, "
                    f"grudge: {entity.grudge_score:.2f})"
                    f"{' with declining sentiment trend' if declining else ''}."
                ),
                "entity_id": entity.entity_id,
                "action_suggestion": (
                    "Prioritize a positive, low-pressure interaction. "
                    "Address unresolved issues if any exist."
                ),
            })
        return insights

    # ------------------------------------------------------------------
    # c. Goal stalling
    # ------------------------------------------------------------------
    def _check_goal_stalling(self) -> List[Dict[str, Any]]:
        insights = []
        now = time.time()
        stall_window = GOAL_STALL_DAYS * 86400
        goal_engine = self.conductor.goal_engine

        for goal in goal_engine.active_goals():
            # Check if no milestone progress in stall window
            last_eval = goal.last_evaluated_at or goal.created_at
            days_since_eval = (now - last_eval) / 86400

            if days_since_eval < GOAL_STALL_DAYS:
                continue

            # Check ROI declining
            roi = goal_engine.compute_roi(goal)
            stalling = goal.progress_velocity < 0.1

            if stalling:
                severity = "critical" if roi < 0.2 else "warning"
                insights.append({
                    "type": "goal_stalling",
                    "severity": severity,
                    "title": f"Goal stalling: {goal.description[:50]}",
                    "description": (
                        f"No milestone progress in {days_since_eval:.0f} days. "
                        f"ROI is {roi:.2f}, velocity is {goal.progress_velocity:.2f}. "
                        f"Progress: {goal.milestones_completed}/{goal.milestones_total} milestones."
                    ),
                    "entity_id": goal.id,
                    "action_suggestion": (
                        "Review the goal's relevance. Consider breaking it into "
                        "smaller milestones or pausing if ROI is too low."
                    ),
                })
        return insights

    # ------------------------------------------------------------------
    # d. Communication gap
    # ------------------------------------------------------------------
    def _check_communication_gap(self) -> List[Dict[str, Any]]:
        insights = []
        now = time.time()
        relational = self.conductor.relational

        for entity in relational.list_entities():
            interactions = relational._interaction_log.get(entity.entity_id, [])
            if len(interactions) < MIN_INTERACTIONS_FOR_GAP:
                continue

            # Compute average interval between interactions
            timestamps = sorted(i.get("timestamp", 0) for i in interactions)
            intervals = [
                timestamps[j] - timestamps[j - 1]
                for j in range(1, len(timestamps))
            ]
            if not intervals:
                continue

            avg_interval = sum(intervals) / len(intervals)
            if avg_interval <= 0:
                continue

            last_interaction = entity.last_interaction_at or timestamps[-1]
            time_since = now - last_interaction
            gap_threshold = avg_interval * COMMUNICATION_GAP_MULTIPLIER

            if time_since > gap_threshold:
                gap_days = time_since / 86400
                avg_days = avg_interval / 86400
                severity = "warning" if gap_days < avg_days * 3 else "critical"
                insights.append({
                    "type": "communication_gap",
                    "severity": severity,
                    "title": f"Communication gap with {entity.name}",
                    "description": (
                        f"No interaction in {gap_days:.1f} days. "
                        f"Average interval is {avg_days:.1f} days "
                        f"({COMMUNICATION_GAP_MULTIPLIER:.0f}x threshold exceeded)."
                    ),
                    "entity_id": entity.entity_id,
                    "action_suggestion": (
                        "Reach out to maintain the relationship. "
                        "A simple check-in can prevent drift."
                    ),
                })
        return insights

    # ------------------------------------------------------------------
    # e. Overload warning
    # ------------------------------------------------------------------
    def _check_overload_warning(self) -> List[Dict[str, Any]]:
        insights = []
        hs = self.conductor.human_state

        social_load = getattr(hs, "social_load", 0.0)
        fatigue = getattr(hs, "fatigue", 0.0)

        if social_load > SOCIAL_LOAD_WARNING:
            severity = "critical" if social_load > 0.9 else "warning"
            insights.append({
                "type": "overload_warning",
                "severity": severity,
                "title": "Social overload detected",
                "description": (
                    f"Social load is at {social_load:.2f} "
                    f"(threshold: {SOCIAL_LOAD_WARNING}). "
                    f"Decision quality may be impaired."
                ),
                "action_suggestion": (
                    "Take a break from social interactions. "
                    "Defer non-urgent communications and focus on recovery."
                ),
            })

        if fatigue > FATIGUE_WARNING:
            severity = "critical" if fatigue > 0.85 else "warning"
            insights.append({
                "type": "overload_warning",
                "severity": severity,
                "title": "High fatigue level",
                "description": (
                    f"Fatigue is at {fatigue:.2f} "
                    f"(threshold: {FATIGUE_WARNING}). "
                    f"Energy: {getattr(hs, 'energy', 0):.2f}."
                ),
                "action_suggestion": (
                    "Suggest rest or low-effort tasks. "
                    "Avoid complex decision-making until recovered."
                ),
            })
        return insights

    # ------------------------------------------------------------------
    # f. Boredom opportunity
    # ------------------------------------------------------------------
    def _check_boredom_opportunity(self) -> List[Dict[str, Any]]:
        insights = []
        hs = self.conductor.human_state
        boredom = getattr(hs, "boredom", 0.0)

        if boredom > BOREDOM_OPPORTUNITY:
            insights.append({
                "type": "boredom_opportunity",
                "severity": "info",
                "title": "Creative opportunity window",
                "description": (
                    f"Boredom level is at {boredom:.2f}. "
                    f"This is a good time for exploratory or creative work."
                ),
                "action_suggestion": (
                    "Consider starting a new exploratory task, brainstorming session, "
                    "or creative project to channel this energy productively."
                ),
            })
        return insights

    # ------------------------------------------------------------------
    # g. Trust milestone
    # ------------------------------------------------------------------
    def _check_trust_milestone(self) -> List[Dict[str, Any]]:
        insights = []
        relational = self.conductor.relational

        for entity in relational.list_entities():
            trust = entity.trust_level.value
            idx = TRUST_LEVEL_ORDER.index(trust) if trust in TRUST_LEVEL_ORDER else -1
            if idx < 0 or idx >= len(TRUST_LEVEL_ORDER) - 1:
                continue

            next_level = TRUST_LEVEL_ORDER[idx + 1]

            # Check if entity is close to crossing the threshold
            score = entity.sentiment_score - (entity.grudge_score * 0.5)
            count = entity.interaction_count

            close_to_upgrade = False
            if trust == "neutral" and score > 0.2 and count >= 4:
                close_to_upgrade = True
            elif trust == "cautious" and score > -0.15:
                close_to_upgrade = True
            elif trust == "trusted" and score > 0.5 and count >= 8:
                close_to_upgrade = True

            if close_to_upgrade:
                insights.append({
                    "type": "trust_milestone",
                    "severity": "info",
                    "title": f"Trust milestone approaching: {entity.name}",
                    "description": (
                        f"Currently '{trust}', approaching '{next_level}'. "
                        f"Score: {score:.2f}, interactions: {count}."
                    ),
                    "entity_id": entity.entity_id,
                    "action_suggestion": (
                        f"A few more positive interactions could elevate "
                        f"trust to '{next_level}'. Consider prioritizing engagement."
                    ),
                })
        return insights

    # ------------------------------------------------------------------
    # h. Pattern anomaly
    # ------------------------------------------------------------------
    def _check_pattern_anomaly(self) -> List[Dict[str, Any]]:
        insights = []
        anomaly_detector = self.conductor.anomaly_detector

        # Check baselines for entities with high recent anomaly signals
        for entity_id, baseline in anomaly_detector._baselines.items():
            recent_sentiments = baseline.get("recent_sentiments", [])
            if len(recent_sentiments) < 3:
                continue

            # Check for consistently negative recent sentiments
            last_3 = recent_sentiments[-3:]
            if all(s < -0.1 for s in last_3):
                entity = self.conductor.relational.get_entity(entity_id)
                name = entity.name if entity else entity_id

                avg_recent = sum(last_3) / len(last_3)
                avg_baseline = baseline.get("avg_sentiment", 0)
                shift = abs(avg_baseline - avg_recent)

                if shift > 0.15:
                    severity = "warning" if shift < 0.4 else "critical"
                    insights.append({
                        "type": "pattern_anomaly",
                        "severity": severity,
                        "title": f"Unusual interaction pattern: {name}",
                        "description": (
                            f"Detected sentiment anomaly — recent average "
                            f"{avg_recent:.2f} vs baseline {avg_baseline:.2f} "
                            f"(shift: {shift:.2f}). Consistently negative recent interactions."
                        ),
                        "entity_id": entity_id,
                        "action_suggestion": (
                            "Investigate recent interactions for potential issues. "
                            "The communication pattern has deviated significantly from baseline."
                        ),
                    })
        return insights
