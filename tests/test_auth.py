"""Tests for APIKeyManager and RateLimiter — authentication and rate limiting."""

import time
import pytest
from unittest.mock import patch

from humane.auth import APIKeyManager, RateLimiter
from humane.core.store import Store


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_auth.db")
    store = Store(db_path)
    store.initialize()
    return store


@pytest.fixture
def key_manager(tmp_db):
    return APIKeyManager(tmp_db)


@pytest.fixture
def rate_limiter():
    return RateLimiter(max_requests=5, window_seconds=60)


class TestGenerateKey:
    def test_generates_valid_key_with_prefix(self, key_manager):
        key = key_manager.generate_key()
        assert key.startswith("hm_")
        assert len(key) > 10

    def test_each_key_is_unique(self, key_manager):
        key1 = key_manager.generate_key()
        key2 = key_manager.generate_key()
        assert key1 != key2


class TestValidateKey:
    def test_validates_correct_key(self, key_manager):
        key = key_manager.generate_key()
        assert key_manager.validate_key(key) is True

    def test_rejects_invalid_key(self, key_manager):
        assert key_manager.validate_key("hm_invalidkey12345678") is False

    def test_rejects_empty_key(self, key_manager):
        assert key_manager.validate_key("") is False

    def test_rejects_key_without_prefix(self, key_manager):
        assert key_manager.validate_key("no_prefix_key") is False

    def test_validate_updates_usage_stats(self, key_manager):
        key = key_manager.generate_key()
        key_manager.validate_key(key)
        keys = key_manager.list_keys()
        assert len(keys) == 1
        assert keys[0]["request_count"] == 1
        assert keys[0]["last_used"] is not None


class TestListKeys:
    def test_list_keys_masks_key(self, key_manager):
        key_manager.generate_key()
        keys = key_manager.list_keys()
        assert len(keys) == 1
        preview = keys[0]["key_preview"]
        assert preview.startswith("hm_...")
        # Should show only last 4 chars after prefix
        assert len(preview) == len("hm_...") + 4

    def test_list_keys_returns_metadata(self, key_manager):
        key_manager.generate_key()
        keys = key_manager.list_keys()
        assert "id" in keys[0]
        assert "created_at" in keys[0]
        assert "request_count" in keys[0]


class TestRevokeKey:
    def test_revoke_key_removes_it(self, key_manager):
        key = key_manager.generate_key()
        keys_before = key_manager.list_keys()
        assert len(keys_before) == 1

        key_id = keys_before[0]["id"]
        key_manager.revoke_key(key_id)

        keys_after = key_manager.list_keys()
        assert len(keys_after) == 0

    def test_revoked_key_no_longer_validates(self, key_manager):
        key = key_manager.generate_key()
        key_id = key_manager.list_keys()[0]["id"]
        key_manager.revoke_key(key_id)
        assert key_manager.validate_key(key) is False


class TestRateLimiter:
    def test_allows_within_limit(self, rate_limiter):
        for _ in range(5):
            allowed, remaining, reset_at = rate_limiter.check("client1")
            assert allowed is True

    def test_blocks_over_limit(self, rate_limiter):
        # Exhaust the limit
        for _ in range(5):
            rate_limiter.check("client1")

        allowed, remaining, reset_at = rate_limiter.check("client1")
        assert allowed is False
        assert remaining == 0

    def test_remaining_decrements(self, rate_limiter):
        _, remaining1, _ = rate_limiter.check("client2")
        _, remaining2, _ = rate_limiter.check("client2")
        assert remaining2 < remaining1

    def test_different_clients_independent(self, rate_limiter):
        # Exhaust client1
        for _ in range(5):
            rate_limiter.check("client1")

        # client2 should still be allowed
        allowed, _, _ = rate_limiter.check("client2")
        assert allowed is True

    def test_headers_returns_expected_keys(self, rate_limiter):
        allowed, remaining, reset_at = rate_limiter.check("client3")
        headers = rate_limiter.headers(allowed, remaining, reset_at)
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers
        assert headers["X-RateLimit-Limit"] == "5"
