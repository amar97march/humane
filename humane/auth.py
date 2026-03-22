"""API authentication and rate limiting for the Humane API."""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from typing import Optional

from humane.core.store import Store


class APIKeyManager:
    """Manages API keys stored in the database."""

    KEY_PREFIX = "hm_"

    def __init__(self, store: Store):
        self.store = store

    def generate_key(self) -> str:
        """Generate a new 32-char API key with 'hm_' prefix and store its hash."""
        raw = secrets.token_hex(16)  # 32 hex chars
        full_key = f"{self.KEY_PREFIX}{raw}"
        key_hash = self._hash_key(full_key)
        key_preview = raw[-4:]
        now = time.time()
        key_id = secrets.token_hex(8)
        with self.store.conn:
            self.store.conn.execute(
                """INSERT INTO api_keys (id, key_hash, key_preview, created_at, last_used, request_count)
                   VALUES (?, ?, ?, ?, NULL, 0)""",
                (key_id, key_hash, key_preview, now),
            )
        return full_key

    def validate_key(self, key: str) -> bool:
        """Check if the given API key is valid (matches a stored hash)."""
        if not key or not key.startswith(self.KEY_PREFIX):
            return False
        key_hash = self._hash_key(key)
        row = self.store.conn.execute(
            "SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        if row is None:
            return False
        # Update last_used and request_count
        with self.store.conn:
            self.store.conn.execute(
                "UPDATE api_keys SET last_used = ?, request_count = request_count + 1 WHERE id = ?",
                (time.time(), row["id"]),
            )
        return True

    def list_keys(self) -> list[dict]:
        """Return all API keys with preview info (never the full key)."""
        rows = self.store.conn.execute(
            "SELECT id, key_preview, created_at, last_used, request_count FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "key_preview": f"hm_...{row['key_preview']}",
                "created_at": row["created_at"],
                "last_used": row["last_used"],
                "request_count": row["request_count"],
            }
            for row in rows
        ]

    def revoke_key(self, key_id: str) -> None:
        """Delete an API key by its id."""
        with self.store.conn:
            self.store.conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # client_id -> deque of timestamps
        self._windows: dict[str, deque] = defaultdict(deque)

    def check(self, client_id: str) -> tuple[bool, int, float]:
        """Check if a request is allowed for the given client.

        Returns (allowed, remaining, reset_at).
        """
        now = time.time()
        window = self._windows[client_id]

        # Evict expired entries
        cutoff = now - self.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= self.max_requests:
            # Rate limited
            reset_at = window[0] + self.window_seconds
            return False, 0, reset_at

        window.append(now)
        remaining = self.max_requests - len(window)
        reset_at = now + self.window_seconds
        return True, remaining, reset_at

    def headers(self, allowed: bool, remaining: int, reset_at: float) -> dict[str, str]:
        """Return rate limit headers."""
        return {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(reset_at)),
        }
