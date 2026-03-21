"""Scheduler — background tick loop for impulses, reminders, and state evolution."""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable, Coroutine, List, Optional, Tuple

logger = logging.getLogger("humane.scheduler")


class Scheduler:
    """Runs periodic tasks: state ticks, impulse checks, reminder checks."""

    def __init__(self, brain, tick_interval: float = 30.0):
        self.brain = brain
        self.tick_interval = tick_interval
        self._running = False
        self._send_message: Optional[Callable] = None  # Set by telegram_bot

    def set_message_sender(self, fn: Callable[[int, str], Coroutine]):
        """Set the function used to send Telegram messages."""
        self._send_message = fn

    async def start(self):
        """Start the background tick loop."""
        self._running = True
        logger.info("Scheduler started (interval: %.1fs)", self.tick_interval)

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error("Scheduler tick error: %s", e)

            await asyncio.sleep(self.tick_interval)

    async def stop(self):
        self._running = False
        logger.info("Scheduler stopped")

    async def _tick(self):
        """One tick: update state, check impulses, check reminders."""
        # 1. Conductor tick (updates HumanState, checks impulses)
        impulse_result = self.brain.conductor.tick()

        # 2. If impulse fired, generate and send messages
        if impulse_result and impulse_result.hold_item is None:
            # Get the impulse event from the action
            from humane.core.models import ImpulseEvent, ImpulseType
            impulse_type_str = impulse_result.action.action_type.replace("impulse_", "")
            try:
                impulse_type = ImpulseType(impulse_type_str)
                event = ImpulseEvent(
                    id="tick_impulse",
                    impulse_type=impulse_type,
                    payload=impulse_result.action.payload,
                    state_snapshot=self.brain.conductor.get_state_snapshot(),
                )
                messages = await self.brain.on_impulse(event)
                await self._send_messages(messages)
            except (ValueError, KeyError):
                pass

        # 3. Check reminders
        try:
            reminder_messages = await self.brain.check_reminders()
            await self._send_messages(reminder_messages)
        except Exception as e:
            logger.debug("Reminder check: %s", e)

    async def _send_messages(self, messages: List[Tuple[int, str]]):
        """Send messages via Telegram."""
        if not self._send_message or not messages:
            return
        for chat_id, text in messages:
            try:
                await self._send_message(chat_id, text)
            except Exception as e:
                logger.error("Failed to send to %d: %s", chat_id, e)
