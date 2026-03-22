"""WhatsApp Bot — async handlers for the Humane companion via WhatsApp Business Cloud API."""

from __future__ import annotations
import asyncio
import logging
import re
import time
from typing import Any, Dict, Optional

import aiohttp

from humane.conductor import Conductor
from humane.core.config import HumaneConfig
from humane.bot.brain import Brain
from humane.bot.conversation import ConversationEngine
from humane.bot.scheduler import Scheduler

logger = logging.getLogger("humane.whatsapp")

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppBot:
    """WhatsApp transport for the Humane bot, using the WhatsApp Business Cloud API."""

    def __init__(self, config: HumaneConfig, brain: Brain, scheduler: Scheduler):
        self.config = config
        self.brain = brain
        self.scheduler = scheduler
        self._session: Optional[aiohttp.ClientSession] = None
        self._processed_message_ids: set[str] = set()  # deduplicate webhook retries
        self._max_processed_cache = 1000

    @property
    def _api_url(self) -> str:
        return f"{GRAPH_API_BASE}/{self.config.whatsapp_phone_number_id}/messages"

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.whatsapp_access_token}",
            "Content-Type": "application/json",
        }

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Sending messages
    # ------------------------------------------------------------------

    async def send_message(self, phone_number: str, text: str):
        """Send a text message via the WhatsApp Business Cloud API."""
        await self._ensure_session()
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": text},
        }
        try:
            async with self._session.post(self._api_url, json=payload, headers=self._headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("WhatsApp send failed (%d): %s", resp.status, body)
                else:
                    logger.debug("WhatsApp message sent to %s", phone_number)
        except Exception as e:
            logger.error("WhatsApp send error: %s", e)

    async def send_interactive_buttons(self, phone_number: str, body_text: str, buttons: list[Dict[str, str]]):
        """Send an interactive button message.

        buttons: list of {"id": "approve_xxx", "title": "Approve"}
        Max 3 buttons per WhatsApp API limits.
        """
        await self._ensure_session()
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": btn["id"], "title": btn["title"][:20]},
                        }
                        for btn in buttons[:3]
                    ]
                },
            },
        }
        try:
            async with self._session.post(self._api_url, json=payload, headers=self._headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("WhatsApp interactive send failed (%d): %s", resp.status, body)
        except Exception as e:
            logger.error("WhatsApp interactive send error: %s", e)

    # ------------------------------------------------------------------
    # Webhook verification (GET /webhook/whatsapp)
    # ------------------------------------------------------------------

    async def handle_verify(self, request) -> Any:
        """Handle the WhatsApp webhook verification challenge (GET)."""
        from aiohttp import web

        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        if mode == "subscribe" and token == self.config.whatsapp_verify_token:
            logger.info("WhatsApp webhook verified successfully")
            return web.Response(text=challenge, content_type="text/plain")

        logger.warning("WhatsApp webhook verification failed (token mismatch)")
        return web.Response(status=403, text="Verification failed")

    # ------------------------------------------------------------------
    # Incoming message handler (POST /webhook/whatsapp)
    # ------------------------------------------------------------------

    async def handle_incoming(self, request) -> Any:
        """Handle incoming WhatsApp webhook events (POST)."""
        from aiohttp import web

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        # WhatsApp sends a specific structure: object -> entry[] -> changes[] -> value
        if body.get("object") != "whatsapp_business_account":
            return web.Response(status=200, text="OK")

        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                # Build a phone -> name lookup from contacts
                contact_names: Dict[str, str] = {}
                for contact in contacts:
                    wa_id = contact.get("wa_id", "")
                    profile = contact.get("profile", {})
                    name = profile.get("name", "")
                    if wa_id:
                        contact_names[wa_id] = name

                for message in messages:
                    await self._process_message(message, contact_names)

        # Always return 200 quickly to avoid webhook retries
        return web.Response(status=200, text="OK")

    async def _process_message(self, message: Dict[str, Any], contact_names: Dict[str, str]):
        """Process a single incoming WhatsApp message."""
        msg_id = message.get("id", "")

        # Deduplicate — WhatsApp may retry delivery
        if msg_id in self._processed_message_ids:
            return
        self._processed_message_ids.add(msg_id)
        if len(self._processed_message_ids) > self._max_processed_cache:
            # Trim oldest entries (set doesn't preserve order, so just clear half)
            self._processed_message_ids = set(list(self._processed_message_ids)[self._max_processed_cache // 2:])

        sender = message.get("from", "")
        msg_type = message.get("type", "")
        user_name = contact_names.get(sender, sender)

        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
            if text:
                await self._handle_text_message(sender, user_name, text)

        elif msg_type == "interactive":
            # Button reply callback
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                button_id = interactive.get("button_reply", {}).get("id", "")
                await self._handle_button_callback(sender, button_id)
            elif interactive.get("type") == "list_reply":
                list_id = interactive.get("list_reply", {}).get("id", "")
                await self._handle_button_callback(sender, list_id)

        elif msg_type in ("image", "audio", "video", "document", "sticker", "location"):
            # Acknowledge unsupported media types
            await self.send_message(
                sender,
                "I received your media, but I can only process text messages right now. Send me a text and I'll help!"
            )

    async def _handle_text_message(self, phone_number: str, user_name: str, text: str):
        """Route a text message through the Brain, just like Telegram does."""
        # Use phone number as chat_id (int). Hash it for consistent mapping.
        chat_id = self._phone_to_chat_id(phone_number)
        user_id = chat_id

        # Check for command-style messages
        text_lower = text.strip().lower()

        if text_lower in ("/start", "hi", "hello", "hey"):
            welcome = (
                f"Hey {user_name or 'there'}! I'm your Humane companion.\n\n"
                "I'm not a regular bot -- I'll remember things, follow up on tasks, "
                "and sometimes bring stuff up on my own.\n\n"
                "Just talk to me naturally. If you want me to remember something, just tell me."
            )
            await self.send_message(phone_number, welcome)
            self.brain._ensure_entity(chat_id, user_name)
            return

        if text_lower.startswith("/remind ") or text_lower.startswith("remind me "):
            task_text = re.sub(r"^(/remind\s+|remind me\s+)", "", text, flags=re.IGNORECASE).strip()
            if task_text:
                remind_at = None
                time_match = re.search(
                    r'(?:in\s+)?(\d+)\s*(hours?|hrs?|minutes?|mins?|days?)',
                    task_text, re.IGNORECASE,
                )
                if time_match:
                    amount = int(time_match.group(1))
                    unit = time_match.group(2).lower()
                    if "hour" in unit or "hr" in unit:
                        remind_at = time.time() + amount * 3600
                    elif "min" in unit:
                        remind_at = time.time() + amount * 60
                    elif "day" in unit:
                        remind_at = time.time() + amount * 86400
                    task_text = task_text[:time_match.start()].strip() or task_text

                if "tomorrow" in task_text.lower():
                    remind_at = time.time() + 86400
                    task_text = task_text.lower().replace("tomorrow", "").strip()

                self.brain.register_reminder(chat_id, task_text, remind_at)
                if remind_at:
                    hours = (remind_at - time.time()) / 3600
                    if hours < 1:
                        time_str = f"{int(hours * 60)} minutes"
                    elif hours < 24:
                        time_str = f"{hours:.0f} hours"
                    else:
                        time_str = f"{hours / 24:.0f} days"
                    await self.send_message(phone_number, f'Got it -- I\'ll remind you about "{task_text}" in {time_str}.')
                else:
                    await self.send_message(phone_number, f'Noted -- "{task_text}". I\'ll start checking in on this tomorrow.')
                return

        # Default: route through Brain
        response = await self.brain.on_user_message(chat_id, user_id, user_name, text)
        if response:
            await self.send_message(phone_number, response)

    async def _handle_button_callback(self, phone_number: str, button_id: str):
        """Handle interactive button presses (approve/reject holds)."""
        if button_id.startswith("approve_"):
            hold_id = button_id.replace("approve_", "")
            try:
                self.brain.conductor.approve_hold(hold_id)
                await self.send_message(phone_number, "Approved.")
            except Exception as e:
                await self.send_message(phone_number, f"Could not approve: {e}")

        elif button_id.startswith("reject_"):
            hold_id = button_id.replace("reject_", "")
            try:
                self.brain.conductor.reject_hold(hold_id)
                await self.send_message(phone_number, "Rejected.")
            except Exception as e:
                await self.send_message(phone_number, f"Could not reject: {e}")

    # ------------------------------------------------------------------
    # Scheduler integration
    # ------------------------------------------------------------------

    def setup_scheduler(self):
        """Wire the scheduler to send messages via WhatsApp.

        This adds a WhatsApp sender alongside any existing Telegram sender.
        The scheduler's _send_messages iterates (chat_id, text) pairs.
        We register a sender that maps chat_ids back to phone numbers.
        """
        # Keep a reverse map: chat_id -> phone_number
        # This gets populated as users message in.
        async def whatsapp_sender(chat_id: int, text: str):
            phone = self._chat_id_to_phone(chat_id)
            if phone:
                await self.send_message(phone, text)

        # If the scheduler already has a telegram sender, wrap both
        existing_sender = self.scheduler._send_message

        async def combined_sender(chat_id: int, text: str):
            if existing_sender:
                try:
                    await existing_sender(chat_id, text)
                except Exception:
                    pass
            await whatsapp_sender(chat_id, text)

        self.scheduler.set_message_sender(combined_sender)

    # ------------------------------------------------------------------
    # Phone <-> chat_id mapping
    # ------------------------------------------------------------------

    # We store a bidirectional mapping so the scheduler can send proactive messages.
    _phone_chat_map: Dict[str, int] = {}
    _chat_phone_map: Dict[int, str] = {}

    @classmethod
    def _phone_to_chat_id(cls, phone_number: str) -> int:
        """Convert a phone number string to a consistent integer chat_id.

        Uses a stable hash so the same phone always maps to the same chat_id.
        Also stores the mapping for reverse lookups.
        """
        if phone_number in cls._phone_chat_map:
            return cls._phone_chat_map[phone_number]

        # Use a simple stable integer derivation (abs of hash, but deterministic)
        # We prefix with 9 to avoid collisions with Telegram chat_ids which are typically smaller.
        chat_id = int("9" + "".join(c for c in phone_number if c.isdigit())[-10:].zfill(10))
        cls._phone_chat_map[phone_number] = chat_id
        cls._chat_phone_map[chat_id] = phone_number
        return chat_id

    @classmethod
    def _chat_id_to_phone(cls, chat_id: int) -> Optional[str]:
        """Reverse lookup: get phone number from chat_id."""
        return cls._chat_phone_map.get(chat_id)

    # ------------------------------------------------------------------
    # Hold queue notifications with interactive buttons
    # ------------------------------------------------------------------

    async def notify_hold(self, phone_number: str, hold_id: str, action_type: str, reason: str):
        """Send a hold notification with approve/reject buttons."""
        body_text = (
            f"Action held: {action_type}\n"
            f"Reason: {reason}\n\n"
            "What would you like to do?"
        )
        buttons = [
            {"id": f"approve_{hold_id}", "title": "Approve"},
            {"id": f"reject_{hold_id}", "title": "Reject"},
        ]
        await self.send_interactive_buttons(phone_number, body_text, buttons)
