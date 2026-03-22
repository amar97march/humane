"""Feedback loop — turns approved/rejected actions into fine-tuning training data."""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from humane.core.store import Store
from humane.core.config import HumaneConfig


class FeedbackCollector:
    """Scans resolved holds and conversations to build training data."""

    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------------
    # Hold-based training pairs
    # ------------------------------------------------------------------

    def collect_from_holds(self) -> list[dict]:
        """Scan resolved hold items and create training pairs.

        For approved: {input, output: "proceed", confidence, context}
        For rejected: {input, output: "reject", confidence, context}
        """
        items = self.store.get_hold_queue(include_resolved=True)
        pairs: list[dict] = []
        for item in items:
            if not item.resolved or item.resolution is None:
                continue

            action_desc = (
                f"{item.action.action_type}: "
                f"{json.dumps(item.action.payload, default=str)}"
            )

            if item.resolution == "approved":
                output = "proceed"
            elif item.resolution == "rejected":
                output = "reject"
            else:
                continue

            pairs.append({
                "input": action_desc,
                "output": output,
                "confidence": round(item.adjusted_confidence, 4),
                "context": {
                    "gate_reasons": item.hold_reason,
                    "hold_source": item.hold_source,
                    "original_confidence": round(item.action.confidence, 4),
                },
                "timestamp": item.created_at,
            })
        return pairs

    # ------------------------------------------------------------------
    # Conversation-based training pairs
    # ------------------------------------------------------------------

    def collect_from_conversations(self) -> list[dict]:
        """Extract positive/negative conversation patterns.

        Messages with sentiment > 0.7  => good response patterns
        Messages with sentiment < -0.3 => patterns to avoid
        """
        rows = self.store.conn.execute(
            """SELECT id, chat_id, user_id, role, content, sentiment, category, created_at
               FROM conversations ORDER BY created_at ASC"""
        ).fetchall()

        pairs: list[dict] = []
        for row in rows:
            sentiment = row["sentiment"] or 0.0
            content = self.store._dec(row["content"]) if row["content"] else ""
            role = row["role"]

            if role == "assistant" and sentiment > 0.7:
                pairs.append({
                    "input": f"conversation:{row['category'] or 'general'}",
                    "output": "positive_pattern",
                    "confidence": round(sentiment, 4),
                    "context": {
                        "content_preview": content[:200],
                        "category": row["category"],
                        "sentiment": round(sentiment, 4),
                    },
                    "timestamp": row["created_at"],
                })
            elif sentiment < -0.3:
                pairs.append({
                    "input": f"conversation:{row['category'] or 'general'}",
                    "output": "negative_pattern",
                    "confidence": round(abs(sentiment), 4),
                    "context": {
                        "content_preview": content[:200],
                        "category": row["category"],
                        "sentiment": round(sentiment, 4),
                    },
                    "timestamp": row["created_at"],
                })
        return pairs

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_training_data(self, format: str = "jsonl") -> str:
        """Export training data as JSONL or CSV."""
        hold_pairs = self.collect_from_holds()
        conv_pairs = self.collect_from_conversations()
        all_pairs = hold_pairs + conv_pairs
        all_pairs.sort(key=lambda p: p.get("timestamp", 0))

        if format == "csv":
            return self._to_csv(all_pairs)
        return self._to_jsonl(all_pairs)

    def _to_jsonl(self, pairs: list[dict]) -> str:
        lines: list[str] = []
        for p in pairs:
            lines.append(json.dumps(p, default=str))
        return "\n".join(lines)

    def _to_csv(self, pairs: list[dict]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["input", "output", "confidence", "context", "timestamp"])
        for p in pairs:
            writer.writerow([
                p["input"],
                p["output"],
                p["confidence"],
                json.dumps(p["context"], default=str),
                p.get("timestamp", ""),
            ])
        return output.getvalue()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Training data stats: total samples, approve/reject ratio, avg confidence."""
        hold_pairs = self.collect_from_holds()
        conv_pairs = self.collect_from_conversations()
        all_pairs = hold_pairs + conv_pairs

        total = len(all_pairs)
        if total == 0:
            return {
                "total_samples": 0,
                "hold_samples": 0,
                "conversation_samples": 0,
                "approve_count": 0,
                "reject_count": 0,
                "positive_pattern_count": 0,
                "negative_pattern_count": 0,
                "approval_rate": 0.0,
                "avg_confidence_approved": 0.0,
                "avg_confidence_rejected": 0.0,
                "data_quality": "insufficient",
            }

        approved = [p for p in hold_pairs if p["output"] == "proceed"]
        rejected = [p for p in hold_pairs if p["output"] == "reject"]
        positive = [p for p in conv_pairs if p["output"] == "positive_pattern"]
        negative = [p for p in conv_pairs if p["output"] == "negative_pattern"]

        approve_count = len(approved)
        reject_count = len(rejected)
        hold_total = approve_count + reject_count

        avg_conf_approved = (
            round(sum(p["confidence"] for p in approved) / approve_count, 4)
            if approve_count else 0.0
        )
        avg_conf_rejected = (
            round(sum(p["confidence"] for p in rejected) / reject_count, 4)
            if reject_count else 0.0
        )

        approval_rate = (
            round(approve_count / hold_total, 4) if hold_total else 0.0
        )

        # Data quality rating
        if total >= 100:
            quality = "good"
        elif total >= 30:
            quality = "moderate"
        elif total >= 10:
            quality = "minimal"
        else:
            quality = "insufficient"

        return {
            "total_samples": total,
            "hold_samples": len(hold_pairs),
            "conversation_samples": len(conv_pairs),
            "approve_count": approve_count,
            "reject_count": reject_count,
            "positive_pattern_count": len(positive),
            "negative_pattern_count": len(negative),
            "approval_rate": approval_rate,
            "avg_confidence_approved": avg_conf_approved,
            "avg_confidence_rejected": avg_conf_rejected,
            "data_quality": quality,
        }


class ThresholdOptimizer:
    """Recommends optimal thresholds based on approval history."""

    # Engine-level thresholds and their config keys
    ENGINE_THRESHOLDS = {
        "values_boundary": "confidence_threshold",
        "social_risk": "social_risk_block_threshold",
        "dissent": "dissent_threshold",
        "anomaly": "anomaly_hard_threshold",
    }

    def __init__(self, store: Store, config: HumaneConfig):
        self.store = store
        self.config = config

    def analyze(self) -> dict:
        """Recommend optimal thresholds based on approval history.

        - Approval rate > 90%: suggest lowering confidence threshold (too cautious)
        - Rejection rate > 50%: suggest raising confidence threshold (too aggressive)
        - Per-engine recommendations based on hold_source approval rates
        """
        items = self.store.get_hold_queue(include_resolved=True)
        resolved = [i for i in items if i.resolved and i.resolution in ("approved", "rejected")]

        total = len(resolved)
        if total == 0:
            return {
                "status": "insufficient_data",
                "message": "No resolved hold items to analyze",
                "total_resolved": 0,
                "recommendations": [],
            }

        approved = [i for i in resolved if i.resolution == "approved"]
        rejected = [i for i in resolved if i.resolution == "rejected"]
        approval_rate = len(approved) / total
        rejection_rate = len(rejected) / total

        recommendations: list[dict] = []

        # Global confidence threshold recommendation
        current_conf = self.config.confidence_threshold
        if approval_rate > 0.9 and total >= 10:
            suggested = round(max(current_conf - 0.05, 0.3), 2)
            recommendations.append({
                "parameter": "confidence_threshold",
                "current": current_conf,
                "recommended": suggested,
                "reason": (
                    f"Approval rate is {approval_rate:.0%} — agent may be too cautious. "
                    f"Lowering threshold from {current_conf} to {suggested} "
                    f"would reduce unnecessary holds."
                ),
                "impact": "fewer_holds",
                "confidence": "high" if total >= 30 else "moderate",
            })
        elif rejection_rate > 0.5 and total >= 10:
            suggested = round(min(current_conf + 0.05, 0.95), 2)
            recommendations.append({
                "parameter": "confidence_threshold",
                "current": current_conf,
                "recommended": suggested,
                "reason": (
                    f"Rejection rate is {rejection_rate:.0%} — agent may be too aggressive. "
                    f"Raising threshold from {current_conf} to {suggested} "
                    f"would catch more problematic actions."
                ),
                "impact": "more_holds",
                "confidence": "high" if total >= 30 else "moderate",
            })

        # Per-engine recommendations
        engine_stats: dict[str, dict] = {}
        for item in resolved:
            source = item.hold_source
            if source not in engine_stats:
                engine_stats[source] = {"approved": 0, "rejected": 0, "total": 0}
            engine_stats[source]["total"] += 1
            if item.resolution == "approved":
                engine_stats[source]["approved"] += 1
            else:
                engine_stats[source]["rejected"] += 1

        for engine, stats in engine_stats.items():
            if stats["total"] < 5:
                continue
            engine_approval = stats["approved"] / stats["total"]
            config_key = self.ENGINE_THRESHOLDS.get(engine)
            if not config_key:
                continue
            current_val = getattr(self.config, config_key, None)
            if current_val is None:
                continue

            if engine_approval > 0.9:
                suggested = round(max(current_val - 0.05, 0.2), 2)
                recommendations.append({
                    "parameter": config_key,
                    "engine": engine,
                    "current": current_val,
                    "recommended": suggested,
                    "reason": (
                        f"Engine '{engine}' holds are approved {engine_approval:.0%} of the time. "
                        f"Consider relaxing {config_key} from {current_val} to {suggested}."
                    ),
                    "impact": "fewer_holds",
                    "confidence": "high" if stats["total"] >= 20 else "moderate",
                })
            elif engine_approval < 0.4:
                suggested = round(min(current_val + 0.05, 0.95), 2)
                recommendations.append({
                    "parameter": config_key,
                    "engine": engine,
                    "current": current_val,
                    "recommended": suggested,
                    "reason": (
                        f"Engine '{engine}' holds are rejected {1 - engine_approval:.0%} of the time. "
                        f"Consider tightening {config_key} from {current_val} to {suggested}."
                    ),
                    "impact": "more_holds",
                    "confidence": "high" if stats["total"] >= 20 else "moderate",
                })

        return {
            "status": "ok",
            "total_resolved": total,
            "approval_rate": round(approval_rate, 4),
            "rejection_rate": round(rejection_rate, 4),
            "engine_stats": engine_stats,
            "recommendations": recommendations,
        }

    def auto_tune(self, dry_run: bool = True) -> dict:
        """Apply recommended threshold changes.

        dry_run=True:  shows what would change
        dry_run=False: applies changes to config
        """
        analysis = self.analyze()
        if analysis["status"] != "ok":
            return {
                "status": analysis["status"],
                "message": analysis.get("message", "Cannot auto-tune"),
                "changes": [],
            }

        changes: list[dict] = []
        for rec in analysis["recommendations"]:
            change = {
                "parameter": rec["parameter"],
                "current": rec["current"],
                "recommended": rec["recommended"],
                "reason": rec["reason"],
                "applied": False,
            }
            if not dry_run:
                setattr(self.config, rec["parameter"], rec["recommended"])
                change["applied"] = True
            changes.append(change)

        return {
            "status": "ok",
            "dry_run": dry_run,
            "changes": changes,
            "total_changes": len(changes),
        }
