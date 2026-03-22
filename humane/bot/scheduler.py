"""Scheduler — background tick loop for impulses, reminders, digest, and state evolution."""

from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Callable, Coroutine, List, Optional, Tuple

logger = logging.getLogger("humane.scheduler")


class Scheduler:
    """Runs periodic tasks: state ticks, impulse checks, reminder checks, daily digest, retention."""

    def __init__(self, brain, tick_interval: float = 30.0):
        self.brain = brain
        self.tick_interval = tick_interval
        self._running = False
        self._send_message: Optional[Callable] = None  # Set by telegram_bot
        self._last_digest_date: Optional[str] = None  # Track last digest date to avoid duplicates
        self._last_retention_date: Optional[str] = None  # Track last retention run date

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
        """One tick: update state, check impulses, check reminders, check digest."""
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

        # 4. Check if daily digest should be sent
        await self._check_digest()

        # 5. Check if retention policies should run
        await self._check_retention()

    async def _check_digest(self):
        """Send daily digest at the configured hour if digest is enabled."""
        try:
            config = self.brain.conductor.config
            if not getattr(config, "digest_enabled", True):
                return

            digest_hour = getattr(config, "digest_hour", 8)
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # Only send once per day, at or after the digest hour
            if now.hour >= digest_hour and self._last_digest_date != today_str:
                self._last_digest_date = today_str

                from humane.digest import DailyDigest
                digest = DailyDigest(self.brain.conductor, config)
                text = digest.format_text()

                if self._send_message:
                    # Send to all known chat_ids from conversations
                    conn = self.brain.conductor.store.conn
                    rows = conn.execute(
                        "SELECT DISTINCT chat_id FROM conversations"
                    ).fetchall()
                    chat_ids = [row["chat_id"] for row in rows]

                    for chat_id in chat_ids:
                        try:
                            await self._send_message(chat_id, text)
                        except Exception as e:
                            logger.error("Failed to send digest to %d: %s", chat_id, e)

                    if chat_ids:
                        logger.info("Daily digest sent to %d chat(s)", len(chat_ids))
                    else:
                        logger.info("Daily digest generated but no chat_ids to send to")
                else:
                    logger.info("Daily digest generated (no message sender configured)")

                self.brain.conductor.event_log.log("daily_digest_sent", "scheduler", {
                    "date": today_str,
                    "digest_hour": digest_hour,
                })
        except Exception as e:
            logger.error("Digest check error: %s", e)

    async def _check_retention(self):
        """Run data retention policies daily at the configured hour."""
        try:
            config = self.brain.conductor.config
            if not getattr(config, "retention_enabled", False):
                return

            retention_hour = getattr(config, "retention_run_hour", 3)
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            if now.hour >= retention_hour and self._last_retention_date != today_str:
                self._last_retention_date = today_str

                from humane.retention import RetentionManager
                mgr = RetentionManager(self.brain.conductor.store, config)
                results = mgr.apply_policies()

                self.brain.conductor.event_log.log("retention_applied", "scheduler", {
                    "date": today_str,
                    "retention_hour": retention_hour,
                    **results,
                })

                logger.info("Retention policies applied: %s", results)
        except Exception as e:
            logger.error("Retention check error: %s", e)

    async def _send_messages(self, messages: List[Tuple[int, str]]):
        """Send messages via Telegram."""
        if not self._send_message or not messages:
            return
        for chat_id, text in messages:
            try:
                await self._send_message(chat_id, text)
            except Exception as e:
                logger.error("Failed to send to %d: %s", chat_id, e)
