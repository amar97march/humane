from __future__ import annotations

import time
from typing import Dict, List, Optional
from uuid import uuid4

from humane.core.store import Store


class EventLog:
    def __init__(self, store: Store):
        self.store = store

    def log(self, event_type: str, engine: str, data: Dict) -> str:
        event_id = str(uuid4())
        self.store.add_event(event_id, event_type, engine, data)
        return event_id

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
