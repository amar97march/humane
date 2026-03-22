from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from humane.core.store import Store

if TYPE_CHECKING:
    from humane.webhooks import WebhookManager

logger = logging.getLogger("humane.events")


class EventLog:
    def __init__(self, store: Store, webhook_manager: Optional[WebhookManager] = None):
        self.store = store
        self.webhook_manager: Optional[WebhookManager] = webhook_manager

    def set_webhook_manager(self, manager: WebhookManager) -> None:
        """Attach a webhook manager after construction (avoids circular init)."""
        self.webhook_manager = manager

    def log(self, event_type: str, engine: str, data: Dict) -> str:
        event_id = str(uuid4())
        self.store.add_event(event_id, event_type, engine, data)

        # Fire webhooks asynchronously if a manager is attached
        if self.webhook_manager is not None:
            self._fire_webhook(event_type, data)

        return event_id

    def _fire_webhook(self, event_type: str, data: Dict) -> None:
        """Schedule webhook delivery without blocking the caller."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.webhook_manager.fire(event_type, data))
        except RuntimeError:
            # No running event loop — skip webhook delivery silently.
            # This happens in synchronous contexts (CLI, tests, etc.).
            logger.debug("No running event loop; skipping webhook fire for %s", event_type)

    def recent(self, limit: int = 50, engine: Optional[str] = None) -> List[Dict]:
        return self.store.list_events(limit=limit, engine=engine)

    def count(self, engine: Optional[str] = None) -> int:
        if engine:
            row = self.store.conn.execute(
                "SELECT COUNT(*) as cnt FROM events WHERE engine = ?", (engine,)
            ).fetchone()
        else:
            row = self.store.conn.execute("SELECT COUNT(*) as cnt FROM events").fetchone()
        return row["cnt"]
