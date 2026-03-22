"""Tests for the Webhook system — registration, delivery, HMAC, retry, filtering."""

import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from humane.core.config import HumaneConfig
from humane.core.store import Store
from humane.core.events import EventLog
from humane.webhooks import WebhookManager, VALID_EVENT_TYPES

_wh_counter = 0


def _make_webhook_manager():
    global _wh_counter
    _wh_counter += 1
    db_path = os.path.join(tempfile.gettempdir(), f"test_wh_{os.getpid()}_{_wh_counter}.db")
    store = Store(db_path)
    store.initialize()
    event_log = EventLog(store)
    return WebhookManager(store=store, event_log=event_log), store


class TestWebhookRegistration:
    def test_register_returns_id(self):
        mgr, _ = _make_webhook_manager()
        wh_id = mgr.register("https://example.com/hook", ["hold_created"])
        assert wh_id is not None
        assert isinstance(wh_id, str)
        assert len(wh_id) > 0

    def test_register_stores_webhook(self):
        mgr, _ = _make_webhook_manager()
        wh_id = mgr.register("https://example.com/hook", ["hold_created", "impulse_fired"])
        webhooks = mgr.list_webhooks()
        assert len(webhooks) == 1
        assert webhooks[0]["id"] == wh_id
        assert webhooks[0]["url"] == "https://example.com/hook"
        assert "hold_created" in webhooks[0]["events"]
        assert "impulse_fired" in webhooks[0]["events"]

    def test_register_with_secret(self):
        mgr, _ = _make_webhook_manager()
        wh_id = mgr.register("https://example.com/hook", ["hold_created"], secret="my-secret")
        webhooks = mgr.list_webhooks()
        assert webhooks[0]["secret"] == "my-secret"

    def test_register_invalid_event_type_raises(self):
        mgr, _ = _make_webhook_manager()
        with pytest.raises(ValueError, match="Invalid event types"):
            mgr.register("https://example.com/hook", ["bogus_event"])

    def test_register_empty_events_raises(self):
        mgr, _ = _make_webhook_manager()
        with pytest.raises(ValueError, match="At least one event"):
            mgr.register("https://example.com/hook", [])

    def test_register_empty_url_raises(self):
        mgr, _ = _make_webhook_manager()
        with pytest.raises(ValueError, match="URL is required"):
            mgr.register("   ", ["hold_created"])

    def test_register_strips_url_whitespace(self):
        mgr, _ = _make_webhook_manager()
        mgr.register("  https://example.com/hook  ", ["hold_created"])
        webhooks = mgr.list_webhooks()
        assert webhooks[0]["url"] == "https://example.com/hook"


class TestWebhookListing:
    def test_list_empty(self):
        mgr, _ = _make_webhook_manager()
        assert mgr.list_webhooks() == []

    def test_list_multiple(self):
        mgr, _ = _make_webhook_manager()
        mgr.register("https://a.com/hook", ["hold_created"])
        mgr.register("https://b.com/hook", ["impulse_fired"])
        webhooks = mgr.list_webhooks()
        assert len(webhooks) == 2


class TestWebhookDeletion:
    def test_unregister_removes_webhook(self):
        mgr, _ = _make_webhook_manager()
        wh_id = mgr.register("https://example.com/hook", ["hold_created"])
        mgr.unregister(wh_id)
        assert mgr.list_webhooks() == []

    def test_unregister_only_removes_target(self):
        mgr, _ = _make_webhook_manager()
        id1 = mgr.register("https://a.com/hook", ["hold_created"])
        id2 = mgr.register("https://b.com/hook", ["impulse_fired"])
        mgr.unregister(id1)
        webhooks = mgr.list_webhooks()
        assert len(webhooks) == 1
        assert webhooks[0]["id"] == id2


class TestHMACSignature:
    def test_sign_payload_produces_valid_hmac(self):
        mgr, _ = _make_webhook_manager()
        payload = b'{"event_type": "test"}'
        secret = "my-secret-key"
        signature = mgr._sign_payload(payload, secret)

        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected

    def test_sign_payload_different_secrets_differ(self):
        mgr, _ = _make_webhook_manager()
        payload = b'{"event_type": "test"}'
        sig1 = mgr._sign_payload(payload, "secret-a")
        sig2 = mgr._sign_payload(payload, "secret-b")
        assert sig1 != sig2


@pytest.mark.asyncio
class TestWebhookDelivery:
    async def test_deliver_success(self):
        mgr, _ = _make_webhook_manager()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_response)

        mgr._session = mock_session

        webhook = {"id": "test-id", "url": "https://example.com/hook", "secret": None}
        payload = {"event_type": "hold_created", "data": {}}
        result = await mgr._deliver(webhook, payload)
        assert result is True

    async def test_deliver_includes_hmac_header_when_secret_set(self):
        mgr, _ = _make_webhook_manager()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_response)

        mgr._session = mock_session

        webhook = {"id": "test-id", "url": "https://example.com/hook", "secret": "my-secret"}
        payload = {"event_type": "hold_created", "data": {}}
        await mgr._deliver(webhook, payload)

        call_args = mock_session.post.call_args
        headers = call_args.kwargs.get("headers", {})
        assert "X-Humane-Signature" in headers

    async def test_deliver_retries_on_failure(self):
        mgr, _ = _make_webhook_manager()

        fail_response = AsyncMock()
        fail_response.status = 500
        fail_response.__aenter__ = AsyncMock(return_value=fail_response)
        fail_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=fail_response)

        mgr._session = mock_session

        webhook = {"id": "test-id", "url": "https://example.com/hook", "secret": None}
        payload = {"event_type": "hold_created", "data": {}}

        # Patch asyncio.sleep to avoid actual delays
        with patch("humane.webhooks.asyncio.sleep", new_callable=AsyncMock):
            result = await mgr._deliver(webhook, payload)

        assert result is False
        # Should have attempted 3 times
        assert mock_session.post.call_count == 3

    async def test_deliver_retries_on_exception(self):
        mgr, _ = _make_webhook_manager()

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=ConnectionError("connection refused"))

        mgr._session = mock_session

        webhook = {"id": "test-id", "url": "https://example.com/hook", "secret": None}
        payload = {"event_type": "hold_created", "data": {}}

        with patch("humane.webhooks.asyncio.sleep", new_callable=AsyncMock):
            result = await mgr._deliver(webhook, payload)

        assert result is False
        assert mock_session.post.call_count == 3

    async def test_deliver_succeeds_on_second_attempt(self):
        mgr, _ = _make_webhook_manager()

        fail_response = AsyncMock()
        fail_response.status = 500
        fail_response.__aenter__ = AsyncMock(return_value=fail_response)
        fail_response.__aexit__ = AsyncMock(return_value=False)

        ok_response = AsyncMock()
        ok_response.status = 200
        ok_response.__aenter__ = AsyncMock(return_value=ok_response)
        ok_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=[fail_response, ok_response])

        mgr._session = mock_session

        webhook = {"id": "test-id", "url": "https://example.com/hook", "secret": None}
        payload = {"event_type": "hold_created", "data": {}}

        with patch("humane.webhooks.asyncio.sleep", new_callable=AsyncMock):
            result = await mgr._deliver(webhook, payload)

        assert result is True
        assert mock_session.post.call_count == 2


@pytest.mark.asyncio
class TestWebhookEventFiltering:
    async def test_fire_only_delivers_to_matching_webhooks(self):
        mgr, store = _make_webhook_manager()

        mgr.register("https://a.com/hook", ["hold_created"])
        mgr.register("https://b.com/hook", ["impulse_fired"])

        delivered_urls = []

        async def mock_deliver(webhook, payload):
            delivered_urls.append(webhook["url"])
            return True

        mgr._deliver = mock_deliver

        await mgr.fire("hold_created", {"some": "data"})

        assert "https://a.com/hook" in delivered_urls
        assert "https://b.com/hook" not in delivered_urls

    async def test_fire_no_matching_webhooks_does_nothing(self):
        mgr, store = _make_webhook_manager()

        mgr.register("https://a.com/hook", ["hold_created"])

        deliver_called = False

        async def mock_deliver(webhook, payload):
            nonlocal deliver_called
            deliver_called = True
            return True

        mgr._deliver = mock_deliver

        await mgr.fire("impulse_fired", {"some": "data"})

        assert deliver_called is False

    async def test_fire_delivers_to_multiple_matching_webhooks(self):
        mgr, store = _make_webhook_manager()

        mgr.register("https://a.com/hook", ["hold_created", "impulse_fired"])
        mgr.register("https://b.com/hook", ["hold_created"])

        delivered_urls = []

        async def mock_deliver(webhook, payload):
            delivered_urls.append(webhook["url"])
            return True

        mgr._deliver = mock_deliver

        await mgr.fire("hold_created", {"some": "data"})

        assert len(delivered_urls) == 2
        assert "https://a.com/hook" in delivered_urls
        assert "https://b.com/hook" in delivered_urls

    async def test_fire_payload_contains_event_type_and_data(self):
        mgr, store = _make_webhook_manager()

        mgr.register("https://a.com/hook", ["hold_created"])

        captured_payload = {}

        async def mock_deliver(webhook, payload):
            captured_payload.update(payload)
            return True

        mgr._deliver = mock_deliver

        await mgr.fire("hold_created", {"key": "value"})

        assert captured_payload["event_type"] == "hold_created"
        assert captured_payload["data"] == {"key": "value"}
        assert "timestamp" in captured_payload
