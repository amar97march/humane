"""Humane Webhook System — async delivery of event notifications to registered endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiohttp

from humane.core.store import Store

logger = logging.getLogger("humane.webhooks")

VALID_EVENT_TYPES = frozenset([
    "hold_created",
    "hold_approved",
    "hold_rejected",
    "impulse_fired",
    "goal_registered",
    "goal_abandoned",
    "goal_paused",
    "memory_added",
    "memory_archived",
    "entity_added",
    "interaction_logged",
    "value_violated",
    "anomaly_detected",
])


class WebhookManager:
    """Manages webhook registrations and async event delivery."""

    def __init__(self, store: Store, event_log: Optional[Any] = None):
        self.store = store
        self.event_log = event_log
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    # --- Registration ---

    def register(self, url: str, events: List[str], secret: Optional[str] = None) -> str:
        """Register a new webhook. Returns the webhook id."""
        invalid = set(events) - VALID_EVENT_TYPES
        if invalid:
            raise ValueError(f"Invalid event types: {', '.join(sorted(invalid))}")
        if not events:
            raise ValueError("At least one event type is required")
        if not url.strip():
            raise ValueError("URL is required")

        webhook_id = str(uuid4())
        self.store.add_webhook(
            webhook_id=webhook_id,
            url=url.strip(),
            events=events,
            secret=secret,
        )
        logger.info("Registered webhook %s for events %s -> %s", webhook_id, events, url)
        return webhook_id

    def unregister(self, webhook_id: str) -> None:
        """Remove a webhook registration."""
        self.store.remove_webhook(webhook_id)
        logger.info("Unregistered webhook %s", webhook_id)

    def list_webhooks(self) -> List[Dict]:
        """Return all registered webhooks."""
        return self.store.list_webhooks()

    # --- Delivery ---

    def _sign_payload(self, payload_bytes: bytes, secret: str) -> str:
        """Compute HMAC-SHA256 signature for a payload."""
        return hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    async def _deliver(self, webhook: Dict, payload: Dict) -> bool:
        """Deliver a payload to a single webhook with retry logic.

        Retries up to 3 attempts with exponential backoff (1s, 2s, 4s).
        Returns True on success, False on failure.
        """
        payload_bytes = json.dumps(payload, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        if webhook.get("secret"):
            signature = self._sign_payload(payload_bytes, webhook["secret"])
            headers["X-Humane-Signature"] = signature

        session = await self._get_session()
        delays = [1, 2, 4]

        for attempt in range(3):
            try:
                async with session.post(
                    webhook["url"],
                    data=payload_bytes,
                    headers=headers,
                ) as resp:
                    if 200 <= resp.status < 300:
                        logger.debug(
                            "Webhook %s delivered successfully (attempt %d)",
                            webhook["id"], attempt + 1,
                        )
                        return True
                    logger.warning(
                        "Webhook %s returned status %d (attempt %d)",
                        webhook["id"], resp.status, attempt + 1,
                    )
            except Exception as exc:
                logger.warning(
                    "Webhook %s delivery failed (attempt %d): %s",
                    webhook["id"], attempt + 1, exc,
                )

            if attempt < 2:
                await asyncio.sleep(delays[attempt])

        # All attempts exhausted — log failure
        self._log_failure(webhook, payload)
        return False

    def _log_failure(self, webhook: Dict, payload: Dict) -> None:
        """Log a delivery failure to the event log."""
        if self.event_log is not None:
            self.event_log.log(
                event_type="webhook_delivery_failed",
                engine="webhooks",
                data={
                    "webhook_id": webhook["id"],
                    "url": webhook["url"],
                    "payload_event": payload.get("event_type"),
                    "timestamp": time.time(),
                },
            )

    async def fire(self, event_type: str, data: Dict) -> None:
        """Fire an event to all matching active webhooks."""
        webhooks = self.store.list_webhooks()
        matching = [
            wh for wh in webhooks
            if wh["active"] and event_type in wh["events"]
        ]

        if not matching:
            return

        payload = {
            "event_type": event_type,
            "data": data,
            "timestamp": time.time(),
        }

        tasks = [self._deliver(wh, payload) for wh in matching]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def test_webhook(self, url: str, secret: Optional[str] = None) -> Dict:
        """Send a test payload to a URL. Returns delivery result."""
        test_payload = {
            "event_type": "webhook_test",
            "data": {"message": "This is a test webhook delivery from Humane."},
            "timestamp": time.time(),
        }

        fake_webhook = {
            "id": "test",
            "url": url,
            "secret": secret,
        }

        payload_bytes = json.dumps(test_payload, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        if secret:
            signature = self._sign_payload(payload_bytes, secret)
            headers["X-Humane-Signature"] = signature

        session = await self._get_session()
        try:
            async with session.post(url, data=payload_bytes, headers=headers) as resp:
                body = await resp.text()
                return {
                    "success": 200 <= resp.status < 300,
                    "status": resp.status,
                    "body": body[:500],
                }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }
