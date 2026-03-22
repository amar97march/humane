"""Brain — the decision engine. When to speak, what to say, how to say it."""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from humane.conductor import Conductor
from humane.core.models import (
    EntityType, ImpulseEvent, MemoryType, ProposedAction, Verdict,
)
from humane.bot.conversation import ConversationEngine, ConversationContext
from humane.categorizer import ConversationCategorizer
from humane.ab_testing import ABTestManager


class Brain:
    """Sits between Telegram and the Conductor. Makes human-like decisions."""

    def __init__(self, conductor: Conductor, conversation: ConversationEngine):
        self.conductor = conductor
        self.conversation = conversation
        self.categorizer = ConversationCategorizer()
        self.ab_manager = ABTestManager(conductor.store)
        self._chat_entity_map: Dict[int, str] = {}  # chat_id -> entity_id
        self._conversation_history: Dict[int, List[Dict[str, str]]] = {}  # chat_id -> messages
        self._deferred: Dict[str, Dict[str, Any]] = {}  # memory_id -> deferral info

    def _ensure_entity(self, chat_id: int, user_name: str = "") -> str:
        """Get or create entity for this chat."""
        if chat_id in self._chat_entity_map:
            return self._chat_entity_map[chat_id]

        # Check if entity exists by name
        for entity in self.conductor.relational.list_entities():
            if entity.name == f"tg_{chat_id}" or entity.name == user_name:
                self._chat_entity_map[chat_id] = entity.entity_id
                return entity.entity_id

        # Create new entity
        name = user_name or f"tg_{chat_id}"
        entity = self.conductor.relational.add_entity(name, EntityType.UNKNOWN)
        self._chat_entity_map[chat_id] = entity.entity_id
        return entity.entity_id

    def _get_history(self, chat_id: int) -> List[Dict[str, str]]:
        return self._conversation_history.get(chat_id, [])

    def _add_to_history(self, chat_id: int, role: str, content: str):
        if chat_id not in self._conversation_history:
            self._conversation_history[chat_id] = []
        self._conversation_history[chat_id].append({"role": role, "content": content})
        # Keep last 50 messages
        self._conversation_history[chat_id] = self._conversation_history[chat_id][-50:]

    async def on_user_message(self, chat_id: int, user_id: int, user_name: str, text: str) -> Optional[str]:
        """Process incoming user message. Returns response or None."""
        entity_id = self._ensure_entity(chat_id, user_name)

        # 1. Analyze sentiment
        sentiment = await self.conversation.analyze_sentiment(text)

        # 2. Update HumanState
        self.conductor.human_state.on_interaction(sentiment)

        # 3. Log interaction in relational memory
        self.conductor.relational.log_interaction(entity_id, sentiment, text[:200])

        # 4. Store as episodic memory
        self.conductor.memory_decay.add_memory(MemoryType.EPISODIC, f"User said: {text[:300]}")

        # 5. Store in conversation table with auto-category
        category = self.categorizer.categorize(text)
        self.conductor.store.add_conversation(str(uuid4()), chat_id, user_id, "user", text, sentiment, category)

        # 6. Check for deferral responses ("not now", "later", "busy")
        defer_response = self._check_deferral(chat_id, text)
        if defer_response:
            self._add_to_history(chat_id, "user", text)
            self._add_to_history(chat_id, "assistant", defer_response)
            self.conductor.store.add_conversation(str(uuid4()), chat_id, 0, "bot", defer_response, 0.0, category)
            return defer_response

        # 7. Find related context (memories, goals, cross-topic links)
        related = self.find_related_context(text)
        pending_reminders = self._get_pending_reminders(chat_id)

        # 8. Build conversation context
        state = self.conductor.get_state_snapshot()
        rel_ctx = self.conductor.relational.get_context(entity_id)
        goals = [
            {
                "description": g.description,
                "milestones_completed": g.milestones_completed,
                "milestones_total": g.milestones_total,
            }
            for g in self.conductor.goal_engine.active_goals()
        ]

        # 8a. Check for active A/B test and override personality
        ab_info = self.ab_manager.get_active_test_for_chat(chat_id)
        ab_personality = ab_info["personality"] if ab_info else None

        ctx = ConversationContext(
            user_message=text,
            human_state=state,
            relational_context=rel_ctx,
            relevant_memories=[m.content for m in related.get("memories", [])],
            active_goals=goals,
            conversation_history=self._get_history(chat_id),
            pending_reminders=[
                {"content": r["content"], "escalation_level": r.get("escalation_level", 0)}
                for r in pending_reminders
            ],
            cross_topic_links=related.get("links", []),
        )

        # If A/B test is active, inject the variant personality as a custom prompt
        if ab_personality:
            ctx.personality = ab_personality

        # 9. Generate response via LLM
        response = await self.conversation.generate_response(ctx)

        # 10. Evaluate response through gate stack
        action = ProposedAction(
            action_type="send_telegram_message",
            payload={"chat_id": chat_id, "text": response},
            confidence=0.8,
            rationale="Reply to user message",
            source="bot",
            target_entity=entity_id,
        )
        result = self.conductor.evaluate(action)

        if result.final_verdict == Verdict.PROCEED:
            self._add_to_history(chat_id, "user", text)
            self._add_to_history(chat_id, "assistant", response)
            response_category = self.categorizer.categorize(response)
            self.conductor.store.add_conversation(str(uuid4()), chat_id, 0, "bot", response, 0.0, response_category)

            # Record A/B test metrics
            if ab_info:
                self.ab_manager.record_result(ab_info["test_id"], chat_id, "response_sentiment", sentiment)
                self.ab_manager.record_result(ab_info["test_id"], chat_id, "approval_rate", 1.0)

            return response

        # If held, send a softer acknowledgment instead
        # Record A/B test metrics for held responses (approval_rate = 0)
        if ab_info:
            self.ab_manager.record_result(ab_info["test_id"], chat_id, "response_sentiment", sentiment)
            self.ab_manager.record_result(ab_info["test_id"], chat_id, "approval_rate", 0.0)

        ack = "Got it, let me think about that."
        self._add_to_history(chat_id, "user", text)
        self._add_to_history(chat_id, "assistant", ack)
        return ack

    async def on_impulse(self, impulse_event: ImpulseEvent) -> List[Tuple[int, str]]:
        """Convert an impulse to messages for relevant chats. Returns [(chat_id, message)]."""
        messages = []
        state = self.conductor.get_state_snapshot()
        goals = [
            {
                "description": g.description,
                "milestones_completed": g.milestones_completed,
                "milestones_total": g.milestones_total,
            }
            for g in self.conductor.goal_engine.active_goals()
        ]
        try:
            memories = [m.content for m in self.conductor.memory_decay.active_memories()[:5]]
        except Exception:
            memories = []

        # Generate natural impulse message
        text = await self.conversation.generate_impulse_message(
            impulse_event.impulse_type.value,
            impulse_event.payload,
            state,
            goals,
            memories,
        )

        # Send to all active chats
        for chat_id in self._chat_entity_map:
            entity_id = self._chat_entity_map[chat_id]
            action = ProposedAction(
                action_type=f"impulse_{impulse_event.impulse_type.value}",
                payload={"chat_id": chat_id, "text": text},
                confidence=0.65,
                rationale=f"Proactive impulse: {impulse_event.impulse_type.value}",
                source="impulse",
                target_entity=entity_id,
            )
            result = self.conductor.evaluate(action)
            if result.final_verdict == Verdict.PROCEED:
                messages.append((chat_id, text))
                self._add_to_history(chat_id, "assistant", text)
                impulse_category = self.categorizer.categorize(text)
                self.conductor.store.add_conversation(str(uuid4()), chat_id, 0, "bot", text, 0.0, impulse_category)

        return messages

    async def check_reminders(self) -> List[Tuple[int, str]]:
        """Check for pending reminders that need to fire. Returns [(chat_id, message)]."""
        messages = []
        now = time.time()

        for chat_id in list(self._chat_entity_map.keys()):
            pending = self.conductor.store.get_pending_reminders(chat_id)
            state = self.conductor.get_state_snapshot()

            for reminder in pending:
                if reminder.get("snoozed_until") and reminder["snoozed_until"] > now:
                    continue
                if reminder.get("next_remind_at", 0) and reminder["next_remind_at"] > now:
                    continue

                escalation = reminder.get("escalation_level", 0)
                text = await self.conversation.generate_reminder(
                    reminder["content"], escalation, state
                )

                # Evaluate through gate stack
                entity_id = self._chat_entity_map.get(chat_id, "")
                action = ProposedAction(
                    action_type="send_reminder",
                    payload={"chat_id": chat_id, "text": text, "reminder_id": reminder["id"]},
                    confidence=0.7 + (escalation * 0.05),  # More confident with each escalation
                    rationale=f"Reminder escalation level {escalation}",
                    source="bot",
                    target_entity=entity_id,
                )
                result = self.conductor.evaluate(action)

                if result.final_verdict == Verdict.PROCEED:
                    messages.append((chat_id, text))
                    self._add_to_history(chat_id, "assistant", text)
                    # Update reminder: next level, next time
                    self.conductor.store.update_reminder(
                        reminder["id"],
                        escalation_level=escalation + 1,
                        last_reminded_at=now,
                        next_remind_at=now + (self.conductor.config.reminder_base_interval_hours * 3600 * (escalation + 1)),
                    )

        return messages

    def _check_deferral(self, chat_id: int, text: str) -> Optional[str]:
        """Check if user is deferring a reminder. Returns response or None."""
        defer_phrases = {"not now", "later", "busy", "remind me later", "snooze", "not yet", "hold on", "in a bit"}
        text_lower = text.lower().strip()

        if not any(phrase in text_lower for phrase in defer_phrases):
            return None

        # Find most recent pending reminder for this chat
        pending = self.conductor.store.get_pending_reminders(chat_id)
        if not pending:
            return None

        latest = pending[0]
        escalation = latest.get("escalation_level", 0)

        # Snooze it
        snooze_hours = max(2, self.conductor.config.reminder_base_interval_hours / (escalation + 1))
        self.conductor.store.update_reminder(
            latest["id"],
            snoozed_until=time.time() + (snooze_hours * 3600),
            escalation_level=escalation + 1,
        )

        # Escalation-aware responses
        if escalation == 0:
            return "No worries, I'll circle back later."
        elif escalation == 1:
            return "Got it. I'll check in again in a few hours."
        elif escalation == 2:
            return f"Alright, but just so you know — this has been pushed {escalation + 1} times now. I'll bring it up again, but we should probably decide soon."
        else:
            return "Okay, deferring again. But honestly? This has been sitting for a while. Next time I bring it up, let's make a call — do it or drop it."

    def find_related_context(self, message: str) -> Dict[str, Any]:
        """Search memories and goals for context related to the current message."""
        result: Dict[str, Any] = {"memories": [], "links": []}

        # Search memories
        words = [w for w in message.lower().split() if len(w) > 3]
        for word in words[:5]:
            found = self.conductor.memory_decay.search(word)
            for mem in found:
                if mem.content not in [m.content for m in result["memories"]]:
                    result["memories"].append(mem)
        result["memories"] = result["memories"][:5]

        # Check goals for relevance
        for goal in self.conductor.goal_engine.active_goals():
            for word in words:
                if word in goal.description.lower():
                    result["links"].append(f"Related goal: {goal.description}")
                    break

        return result

    def _get_pending_reminders(self, chat_id: int) -> List[Dict[str, Any]]:
        """Get pending reminders for a chat."""
        try:
            return self.conductor.store.get_pending_reminders(chat_id)
        except Exception:
            return []

    def register_reminder(self, chat_id: int, content: str, remind_at: Optional[float] = None) -> str:
        """Register a new reminder."""
        memory = self.conductor.memory_decay.add_memory(MemoryType.EPISODIC, f"TASK: {content}", pinned=True)
        reminder_id = str(uuid4())
        next_time = remind_at or (time.time() + self.conductor.config.reminder_base_interval_hours * 3600)
        self.conductor.store.add_reminder(
            reminder_id=reminder_id,
            memory_id=memory.id,
            chat_id=chat_id,
            content=content,
            next_remind_at=next_time,
        )
        return reminder_id
