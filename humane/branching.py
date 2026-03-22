"""Conversation branching — "What would happen if I said X?" simulation.

Runs a hypothetical user message through the full pipeline WITHOUT persisting
any state changes, giving a preview of sentiment, state impact, gate evaluation,
related context, and the predicted response.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

from humane.conductor import Conductor
from humane.core.models import ProposedAction, Verdict

logger = logging.getLogger("humane.branching")


class ConversationBranch:
    """Simulate what would happen if the user said something, without side effects."""

    def __init__(self, conductor: Conductor, conversation_engine=None):
        self.conductor = conductor
        self.conversation = conversation_engine

    async def simulate(self, message: str, chat_id: Optional[str] = None) -> Dict[str, Any]:
        """Simulate a hypothetical user message through the full pipeline.

        Returns a dict with predicted sentiment, state changes, related context,
        gate evaluation result, predicted response, and affected entities.
        Nothing is persisted.
        """
        # Snapshot current state before simulation
        state_before = self.conductor.get_state_snapshot()

        # 1. Sentiment analysis
        predicted_sentiment = 0.0
        if self.conversation:
            try:
                predicted_sentiment = await self.conversation.analyze_sentiment(message)
            except Exception as exc:
                logger.warning("Sentiment analysis failed: %s", exc)
                predicted_sentiment = self._heuristic_sentiment(message)
        else:
            predicted_sentiment = self._heuristic_sentiment(message)

        # 2. Predict state impact (simulate without persisting)
        state_changes = self._predict_state_impact(predicted_sentiment, state_before)

        # 3. Find related context (read-only operation)
        related_context = self._find_related_context(message)

        # 4. Gate evaluation (dry run — we create a ProposedAction but do NOT persist hold items)
        gate_result = self._dry_run_gate(message, chat_id)

        # 5. Generate predicted response (if conversation engine available)
        predicted_response = ""
        if self.conversation:
            try:
                predicted_response = await self._generate_preview_response(
                    message, state_before, related_context, chat_id
                )
            except Exception as exc:
                logger.warning("Response generation failed: %s", exc)
                predicted_response = "(Could not generate preview — LLM unavailable)"
        else:
            predicted_response = "(No conversation engine configured)"

        # 6. Identify affected entities
        entities_affected = self._find_affected_entities(message)

        return {
            "input": message,
            "predicted_sentiment": round(predicted_sentiment, 3),
            "state_changes": state_changes,
            "related_context": related_context,
            "gate_result": gate_result,
            "predicted_response": predicted_response,
            "entities_affected": entities_affected,
        }

    async def compare(self, messages: List[str], chat_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Simulate multiple messages and return side-by-side comparison."""
        results = []
        for msg in messages:
            result = await self.simulate(msg, chat_id)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _heuristic_sentiment(self, message: str) -> float:
        """Simple keyword-based sentiment when no LLM is available."""
        text = message.lower()
        positive = ["thank", "great", "awesome", "love", "happy", "good", "nice",
                     "perfect", "excellent", "wonderful", "amazing", "yes", "sure"]
        negative = ["hate", "angry", "bad", "terrible", "awful", "annoyed", "frustrated",
                     "disappointed", "no", "stop", "worst", "never", "sad", "sorry"]

        pos_count = sum(1 for w in positive if w in text)
        neg_count = sum(1 for w in negative if w in text)

        if pos_count == 0 and neg_count == 0:
            return 0.0
        return round((pos_count - neg_count) / max(pos_count + neg_count, 1), 3)

    def _predict_state_impact(self, sentiment: float, state_before: Dict[str, Any]) -> Dict[str, Any]:
        """Predict how the state would change based on sentiment of the message."""
        # Model the impact: positive sentiment boosts mood/energy, negative drains them
        mood_delta = round(sentiment * 0.15, 4)
        energy_delta = round(sentiment * 0.05, 4)
        fatigue_delta = round(0.02, 4)  # Any interaction adds slight fatigue
        social_load_delta = round(0.05, 4)  # Interactions increase social load
        focus_delta = round(-0.03, 4)  # Interruptions reduce focus slightly
        boredom_delta = round(-0.05, 4)  # Interaction reduces boredom

        return {
            "energy_delta": energy_delta,
            "mood_delta": mood_delta,
            "fatigue_delta": fatigue_delta,
            "social_load_delta": social_load_delta,
            "focus_delta": focus_delta,
            "boredom_delta": boredom_delta,
            "predicted_state": {
                "energy": round(max(0, min(1, state_before.get("energy", 0.8) + energy_delta)), 4),
                "mood": round(max(-1, min(1, state_before.get("mood", 0.0) + mood_delta)), 4),
                "fatigue": round(max(0, min(1, state_before.get("fatigue", 0.0) + fatigue_delta)), 4),
                "social_load": round(max(0, min(1, state_before.get("social_load", 0.0) + social_load_delta)), 4),
                "focus": round(max(0, min(1, state_before.get("focus", 0.7) + focus_delta)), 4),
                "boredom": round(max(0, min(1, state_before.get("boredom", 0.0) + boredom_delta)), 4),
            },
        }

    def _find_related_context(self, message: str) -> List[Dict[str, str]]:
        """Search memories and goals for context related to the message (read-only)."""
        context_items = []

        # Search memories
        words = [w for w in message.lower().split() if len(w) > 3]
        seen_contents = set()
        for word in words[:5]:
            try:
                found = self.conductor.memory_decay.search(word)
                for mem in found:
                    if mem.content not in seen_contents:
                        seen_contents.add(mem.content)
                        context_items.append({
                            "type": "memory",
                            "content": mem.content,
                            "relevance": round(mem.relevance_score, 3),
                        })
            except Exception:
                pass

        # Check goals
        try:
            for goal in self.conductor.goal_engine.active_goals():
                for word in words:
                    if word in goal.description.lower():
                        context_items.append({
                            "type": "goal",
                            "content": goal.description,
                            "relevance": 1.0,
                        })
                        break
        except Exception:
            pass

        return context_items[:10]

    def _dry_run_gate(self, message: str, chat_id: Optional[str] = None) -> Dict[str, Any]:
        """Evaluate the message through the gate stack WITHOUT persisting holds.

        We snapshot the human state, run the gate stack, then compare — but
        we do NOT call _create_hold (the conductor does that internally, so we
        catch the result and roll back).
        """
        action = ProposedAction(
            action_type="simulate_message",
            payload={"message": message, "chat_id": chat_id or "simulation"},
            confidence=0.8,
            rationale="Simulated user message for branching preview",
            source="simulation",
        )

        # Save hold queue length before evaluation
        queue_before = len(self.conductor.get_hold_queue())

        result = self.conductor.evaluate(action)

        # Clean up: if the evaluation created a hold item, remove it
        # (the conductor persists holds internally, so we undo that)
        if result.hold_item:
            try:
                self.conductor.store.resolve_hold_item(result.hold_item.id, "simulation_cleanup")
            except Exception:
                pass

        verdict = result.final_verdict.value
        reasons = [gr.reason for gr in result.gate_results]
        gate_scores = {gr.engine: {"verdict": gr.verdict.value, "score": round(gr.score, 3)}
                       for gr in result.gate_results}

        return {
            "verdict": verdict,
            "reasons": reasons,
            "gate_scores": gate_scores,
            "would_be_held": verdict in ("hold", "defer"),
            "audit_trail": result.audit_trail,
        }

    async def _generate_preview_response(
        self, message: str, state: Dict[str, Any],
        related_context: List[Dict[str, str]], chat_id: Optional[str] = None,
    ) -> str:
        """Generate what the bot would say in response (without persisting)."""
        from humane.bot.conversation import ConversationContext

        goals = []
        try:
            goals = [
                {
                    "description": g.description,
                    "milestones_completed": g.milestones_completed,
                    "milestones_total": g.milestones_total,
                }
                for g in self.conductor.goal_engine.active_goals()
            ]
        except Exception:
            pass

        ctx = ConversationContext(
            user_message=message,
            human_state=state,
            relational_context={},
            relevant_memories=[item["content"] for item in related_context if item["type"] == "memory"],
            active_goals=goals,
            conversation_history=[],
            cross_topic_links=[item["content"] for item in related_context if item["type"] == "goal"],
        )

        return await self.conversation.generate_response(ctx)

    def _find_affected_entities(self, message: str) -> List[Dict[str, str]]:
        """Find entities that might be referenced in the message."""
        affected = []
        try:
            entities = self.conductor.relational.list_entities()
            text_lower = message.lower()
            for entity in entities:
                if entity.name.lower() in text_lower:
                    affected.append({
                        "entity_id": entity.entity_id,
                        "name": entity.name,
                        "type": entity.entity_type.value,
                    })
        except Exception:
            pass
        return affected
