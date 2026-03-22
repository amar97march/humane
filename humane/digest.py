"""Daily Digest — generates a morning summary of agent state, alerts, and activity."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from humane.core.config import HumaneConfig


class DailyDigest:
    """Produces a comprehensive daily digest from the Conductor's engines and store."""

    def __init__(self, conductor, config: HumaneConfig):
        self.conductor = conductor
        self.config = config

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    def generate(self) -> dict:
        """Produce a morning summary dictionary with all digest sections."""
        now = time.time()

        return {
            "generated_at": now,
            "generated_at_iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "stalling_goals": self._stalling_goals(now),
            "pending_holds": self._pending_holds(),
            "neglected_entities": self._neglected_entities(now),
            "sentiment_alerts": self._sentiment_alerts(),
            "anomalies": self._recent_anomalies(now),
            "memory_decay_warnings": self._memory_decay_warnings(),
            "impulse_summary": self._impulse_summary(now),
            "state_summary": self._state_summary(),
        }

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _stalling_goals(self, now: float) -> List[dict]:
        """Goals with ROI < 0.3 or no progress in 7+ days."""
        stalling: List[dict] = []
        seven_days = 7 * 86400

        for goal in self.conductor.goal_engine.active_goals():
            roi = self.conductor.goal_engine.compute_roi(goal)
            last_eval = goal.last_evaluated_at or goal.created_at
            days_stale = (now - last_eval) / 86400

            if roi < 0.3 or days_stale >= 7:
                reasons: List[str] = []
                if roi < 0.3:
                    reasons.append(f"low ROI ({roi:.2f})")
                if days_stale >= 7:
                    reasons.append(f"no progress in {days_stale:.0f} days")
                stalling.append({
                    "id": goal.id,
                    "description": goal.description,
                    "roi": round(roi, 4),
                    "days_since_progress": round(days_stale, 1),
                    "reasons": reasons,
                })

        return stalling

    def _pending_holds(self) -> dict:
        """Count and summary of unresolved hold queue items."""
        queue = self.conductor.get_hold_queue()
        by_source: Dict[str, int] = {}
        for item in queue:
            by_source[item.hold_source] = by_source.get(item.hold_source, 0) + 1

        return {
            "count": len(queue),
            "by_source": by_source,
        }

    def _neglected_entities(self, now: float) -> List[dict]:
        """Entities with no interaction in 14+ days, sorted by days since last contact."""
        fourteen_days = 14 * 86400
        neglected: List[dict] = []

        for entity in self.conductor.relational.list_entities():
            last = entity.last_interaction_at
            if last is None:
                days_since = (now - entity.created_at) / 86400
            else:
                days_since = (now - last) / 86400

            if days_since >= 14:
                neglected.append({
                    "entity_id": entity.entity_id,
                    "name": entity.name,
                    "entity_type": entity.entity_type.value,
                    "days_since_contact": round(days_since, 1),
                    "relationship_health": entity.relationship_health.value,
                })

        neglected.sort(key=lambda x: x["days_since_contact"], reverse=True)
        return neglected

    def _sentiment_alerts(self) -> List[dict]:
        """Entities whose sentiment dropped below -0.3."""
        alerts: List[dict] = []

        for entity in self.conductor.relational.list_entities():
            if entity.sentiment_score < -0.3:
                alerts.append({
                    "entity_id": entity.entity_id,
                    "name": entity.name,
                    "sentiment_score": round(entity.sentiment_score, 3),
                    "relationship_health": entity.relationship_health.value,
                    "trust_level": entity.trust_level.value,
                })

        alerts.sort(key=lambda x: x["sentiment_score"])
        return alerts

    def _recent_anomalies(self, now: float) -> List[dict]:
        """Anomaly events from the last 24 hours."""
        cutoff = now - 86400
        all_events = self.conductor.event_log.recent(limit=200, engine="anomaly")
        anomalies: List[dict] = []

        for event in all_events:
            if event.get("created_at", 0) >= cutoff:
                anomalies.append({
                    "event_type": event.get("event_type", ""),
                    "data": event.get("data", {}),
                    "created_at": event.get("created_at"),
                })

        return anomalies

    def _memory_decay_warnings(self) -> List[dict]:
        """Important (pinned or high-relevance) memories nearing archive threshold."""
        threshold = self.config.memory_retrieval_threshold
        # Warn when relevance is within 50% above the archive threshold
        warn_threshold = threshold * 1.5
        warnings: List[dict] = []

        for memory in self.conductor.memory_decay.active_memories():
            is_important = memory.pinned or memory.relevance_score >= 0.7
            if is_important and memory.relevance_score <= warn_threshold:
                warnings.append({
                    "id": memory.id,
                    "content": memory.content[:100],
                    "memory_type": memory.memory_type.value,
                    "relevance_score": round(memory.relevance_score, 3),
                    "pinned": memory.pinned,
                    "archive_threshold": threshold,
                })

        warnings.sort(key=lambda x: x["relevance_score"])
        return warnings

    def _impulse_summary(self, now: float) -> dict:
        """Impulses fired in the last 24 hours, grouped by type."""
        cutoff = now - 86400
        all_events = self.conductor.event_log.recent(limit=200, engine="impulse")
        by_type: Dict[str, int] = {}
        total = 0

        for event in all_events:
            if event.get("created_at", 0) >= cutoff:
                etype = event.get("event_type", "unknown")
                by_type[etype] = by_type.get(etype, 0) + 1
                total += 1

        return {
            "total": total,
            "by_type": by_type,
        }

    def _state_summary(self) -> dict:
        """Current energy/mood/fatigue snapshot."""
        self.conductor.human_state.tick()
        snapshot = self.conductor.get_state_snapshot()
        return {
            "energy": round(snapshot.get("energy", 0), 3),
            "mood": round(snapshot.get("mood", 0), 3),
            "fatigue": round(snapshot.get("fatigue", 0), 3),
            "boredom": round(snapshot.get("boredom", 0), 3),
            "focus": round(snapshot.get("focus", 0), 3),
            "social_load": round(snapshot.get("social_load", 0), 3),
        }

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    def format_text(self) -> str:
        """Format the digest as readable text for Telegram/WhatsApp."""
        d = self.generate()
        lines: List[str] = []
        ts = datetime.fromtimestamp(d["generated_at"], tz=timezone.utc)
        lines.append(f"Daily Digest — {ts.strftime('%A, %B %d %Y')}")
        lines.append("=" * 40)

        # State
        st = d["state_summary"]
        lines.append("")
        lines.append("STATE")
        lines.append(
            f"  Energy: {st['energy']:.2f}  Mood: {st['mood']:+.2f}  "
            f"Fatigue: {st['fatigue']:.2f}  Focus: {st['focus']:.2f}"
        )

        # Stalling goals
        goals = d["stalling_goals"]
        lines.append("")
        lines.append(f"STALLING GOALS ({len(goals)})")
        if goals:
            for g in goals:
                lines.append(f"  - {g['description']} (ROI: {g['roi']:.2f}, {', '.join(g['reasons'])})")
        else:
            lines.append("  None")

        # Hold queue
        holds = d["pending_holds"]
        lines.append("")
        lines.append(f"PENDING HOLDS: {holds['count']}")
        if holds["by_source"]:
            for src, cnt in holds["by_source"].items():
                lines.append(f"  - {src}: {cnt}")

        # Neglected entities
        neglected = d["neglected_entities"]
        lines.append("")
        lines.append(f"NEGLECTED CONTACTS ({len(neglected)})")
        if neglected:
            for e in neglected[:10]:
                lines.append(f"  - {e['name']} ({e['entity_type']}): {e['days_since_contact']:.0f} days")
        else:
            lines.append("  None")

        # Sentiment alerts
        alerts = d["sentiment_alerts"]
        lines.append("")
        lines.append(f"SENTIMENT ALERTS ({len(alerts)})")
        if alerts:
            for a in alerts:
                lines.append(f"  - {a['name']}: {a['sentiment_score']:+.2f} ({a['relationship_health']})")
        else:
            lines.append("  None")

        # Anomalies
        anomalies = d["anomalies"]
        lines.append("")
        lines.append(f"ANOMALIES (last 24h): {len(anomalies)}")
        if anomalies:
            for a in anomalies[:5]:
                lines.append(f"  - {a['event_type']}")

        # Memory decay warnings
        mem_warns = d["memory_decay_warnings"]
        lines.append("")
        lines.append(f"MEMORY DECAY WARNINGS ({len(mem_warns)})")
        if mem_warns:
            for m in mem_warns[:5]:
                pin_flag = " [pinned]" if m["pinned"] else ""
                lines.append(
                    f"  - {m['content'][:60]}...{pin_flag} "
                    f"(relevance: {m['relevance_score']:.2f})"
                )
        else:
            lines.append("  None")

        # Impulse summary
        imp = d["impulse_summary"]
        lines.append("")
        lines.append(f"IMPULSES (last 24h): {imp['total']}")
        if imp["by_type"]:
            for t, c in imp["by_type"].items():
                lines.append(f"  - {t}: {c}")

        return "\n".join(lines)

    def format_html(self) -> str:
        """Format the digest as HTML for dashboard display."""
        d = self.generate()
        ts = datetime.fromtimestamp(d["generated_at"], tz=timezone.utc)

        def _section(title: str, badge_count: int, body: str) -> str:
            badge_cls = "badge-red" if badge_count > 0 else "badge-green"
            return f"""
            <div class="digest-section">
              <div class="digest-section-header">
                <span class="digest-section-title">{title}</span>
                <span class="badge {badge_cls}">{badge_count}</span>
              </div>
              <div class="digest-section-body">{body}</div>
            </div>"""

        parts: List[str] = []
        parts.append(f'<div class="digest-container">')
        parts.append(f'<div class="digest-header">Daily Digest &mdash; {ts.strftime("%A, %B %d %Y")}</div>')

        # State summary bar
        st = d["state_summary"]
        mood_color = "#3D8B5E" if st["mood"] >= 0 else "#C44D2D"
        parts.append(f"""
        <div class="digest-state-bar">
          <span>Energy: <b>{st['energy']:.2f}</b></span>
          <span>Mood: <b style="color:{mood_color}">{st['mood']:+.2f}</b></span>
          <span>Fatigue: <b>{st['fatigue']:.2f}</b></span>
          <span>Focus: <b>{st['focus']:.2f}</b></span>
        </div>""")

        # Stalling goals
        goals = d["stalling_goals"]
        if goals:
            rows = "".join(
                f'<div class="digest-item"><span class="digest-item-label">{g["description"]}</span>'
                f'<span class="digest-item-detail">ROI {g["roi"]:.2f} &mdash; {", ".join(g["reasons"])}</span></div>'
                for g in goals
            )
        else:
            rows = '<div class="digest-empty">All goals on track</div>'
        parts.append(_section("Stalling Goals", len(goals), rows))

        # Pending holds
        holds = d["pending_holds"]
        if holds["count"] > 0:
            rows = "".join(
                f'<div class="digest-item"><span class="digest-item-label">{src}</span>'
                f'<span class="digest-item-detail">{cnt} item{"s" if cnt != 1 else ""}</span></div>'
                for src, cnt in holds["by_source"].items()
            )
        else:
            rows = '<div class="digest-empty">No pending holds</div>'
        parts.append(_section("Pending Holds", holds["count"], rows))

        # Neglected entities
        neglected = d["neglected_entities"]
        if neglected:
            rows = "".join(
                f'<div class="digest-item"><span class="digest-item-label">{e["name"]}</span>'
                f'<span class="digest-item-detail">{e["days_since_contact"]:.0f} days &mdash; {e["entity_type"]}</span></div>'
                for e in neglected[:10]
            )
        else:
            rows = '<div class="digest-empty">All contacts engaged</div>'
        parts.append(_section("Neglected Contacts", len(neglected), rows))

        # Sentiment alerts
        alerts = d["sentiment_alerts"]
        if alerts:
            rows = "".join(
                f'<div class="digest-item"><span class="digest-item-label">{a["name"]}</span>'
                f'<span class="digest-item-detail">Sentiment {a["sentiment_score"]:+.2f} &mdash; {a["relationship_health"]}</span></div>'
                for a in alerts
            )
        else:
            rows = '<div class="digest-empty">No sentiment concerns</div>'
        parts.append(_section("Sentiment Alerts", len(alerts), rows))

        # Anomalies
        anomalies = d["anomalies"]
        if anomalies:
            rows = "".join(
                f'<div class="digest-item"><span class="digest-item-label">{a["event_type"]}</span></div>'
                for a in anomalies[:5]
            )
        else:
            rows = '<div class="digest-empty">No anomalies detected</div>'
        parts.append(_section("Anomalies (24h)", len(anomalies), rows))

        # Memory decay warnings
        mem_warns = d["memory_decay_warnings"]
        if mem_warns:
            rows = "".join(
                f'<div class="digest-item"><span class="digest-item-label">{m["content"][:60]}...</span>'
                f'<span class="digest-item-detail">Relevance {m["relevance_score"]:.2f}'
                f'{" [pinned]" if m["pinned"] else ""}</span></div>'
                for m in mem_warns[:5]
            )
        else:
            rows = '<div class="digest-empty">No memories at risk</div>'
        parts.append(_section("Memory Decay Warnings", len(mem_warns), rows))

        # Impulse summary
        imp = d["impulse_summary"]
        if imp["total"] > 0:
            rows = "".join(
                f'<div class="digest-item"><span class="digest-item-label">{t}</span>'
                f'<span class="digest-item-detail">{c}</span></div>'
                for t, c in imp["by_type"].items()
            )
        else:
            rows = '<div class="digest-empty">No impulses fired</div>'
        parts.append(_section("Impulses (24h)", imp["total"], rows))

        parts.append("</div>")
        return "\n".join(parts)
