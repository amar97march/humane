"""Humane GDPR — GDPR-compliant personal data export and erasure."""

from __future__ import annotations

import csv
import io
import json
import logging
import time
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from humane.core.config import HumaneConfig, SENSITIVE_FIELDS
from humane.core.store import Store

logger = logging.getLogger("humane.gdpr")

# Config keys to exclude from GDPR export (system paths and API keys)
EXCLUDED_CONFIG_KEYS = frozenset({
    "db_path",
    "api_port",
    "llm_api_key",
    "llm_base_url",
    "telegram_bot_token",
    "whatsapp_access_token",
    "whatsapp_verify_token",
    "whatsapp_phone_number_id",
})


class GDPRExporter:
    """Handles GDPR-compliant personal data export and right-to-erasure."""

    def __init__(self, store: Store, conductor):
        self.store = store
        self.conductor = conductor

    # ------------------------------------------------------------------
    # Export personal data
    # ------------------------------------------------------------------

    def export_personal_data(self, entity_id: Optional[str] = None) -> dict:
        """Export ALL personal data as a JSON-serializable dict.

        If entity_id is provided, exports only data related to that entity.
        Otherwise, exports everything.
        """
        conn = self.store.conn
        data: Dict[str, Any] = {}
        record_counts: Dict[str, int] = {}
        categories_included: List[str] = []

        # 1. Conversations
        if entity_id:
            # Filter conversations that mention the entity
            entity_row = conn.execute(
                "SELECT name FROM entities WHERE entity_id = ?", (entity_id,)
            ).fetchone()
            entity_name = entity_row["name"] if entity_row else entity_id
            rows = conn.execute(
                "SELECT * FROM conversations WHERE content LIKE ? OR content LIKE ? ORDER BY created_at DESC",
                (f"%{entity_id}%", f"%{entity_name}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY created_at DESC"
            ).fetchall()

        conversations = [
            {
                "id": row["id"],
                "chat_id": row["chat_id"],
                "user_id": row["user_id"],
                "role": row["role"],
                "content": row["content"],
                "sentiment": row["sentiment"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        data["conversations"] = conversations
        record_counts["conversations"] = len(conversations)
        if conversations:
            categories_included.append("conversations")

        # 2. Entity profiles
        if entity_id:
            entity_rows = conn.execute(
                "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
            ).fetchall()
        else:
            entity_rows = conn.execute("SELECT * FROM entities").fetchall()

        entities = [
            {
                "entity_id": row["entity_id"],
                "name": row["name"],
                "entity_type": row["entity_type"],
                "sentiment_score": row["sentiment_score"],
                "grudge_score": row["grudge_score"],
                "trust_level": row["trust_level"],
                "relationship_health": row["relationship_health"],
                "disclosure_threshold": row["disclosure_threshold"],
                "interaction_count": row["interaction_count"],
                "last_interaction_at": row["last_interaction_at"],
                "created_at": row["created_at"],
            }
            for row in entity_rows
        ]
        data["entities"] = entities
        record_counts["entities"] = len(entities)
        if entities:
            categories_included.append("entities")

        # 3. Interactions
        if entity_id:
            interaction_rows = conn.execute(
                "SELECT * FROM interactions WHERE entity_id = ? ORDER BY created_at DESC",
                (entity_id,),
            ).fetchall()
        else:
            interaction_rows = conn.execute(
                "SELECT * FROM interactions ORDER BY created_at DESC"
            ).fetchall()

        interactions = [
            {
                "id": row["id"],
                "entity_id": row["entity_id"],
                "sentiment": row["sentiment"],
                "content_summary": row["content_summary"],
                "created_at": row["created_at"],
            }
            for row in interaction_rows
        ]
        data["interactions"] = interactions
        record_counts["interactions"] = len(interactions)
        if interactions:
            categories_included.append("interactions")

        # 4. Memories
        if entity_id:
            # Find memories that reference the entity
            entity_row = conn.execute(
                "SELECT name FROM entities WHERE entity_id = ?", (entity_id,)
            ).fetchone()
            entity_name = entity_row["name"] if entity_row else entity_id
            memory_rows = conn.execute(
                "SELECT * FROM memories WHERE content LIKE ? OR content LIKE ? ORDER BY created_at DESC",
                (f"%{entity_id}%", f"%{entity_name}%"),
            ).fetchall()
        else:
            memory_rows = conn.execute(
                "SELECT * FROM memories ORDER BY created_at DESC"
            ).fetchall()

        memories = [
            {
                "id": row["id"],
                "memory_type": row["memory_type"],
                "content": row["content"],
                "relevance_score": row["relevance_score"],
                "access_count": row["access_count"],
                "pinned": bool(row["pinned"]),
                "archived": bool(row["archived"]),
                "created_at": row["created_at"],
                "last_accessed_at": row["last_accessed_at"],
            }
            for row in memory_rows
        ]
        data["memories"] = memories
        record_counts["memories"] = len(memories)
        if memories:
            categories_included.append("memories")

        # 5. Hold queue items
        if entity_id:
            hold_rows = conn.execute(
                "SELECT * FROM hold_queue WHERE action_json LIKE ? ORDER BY created_at DESC",
                (f"%{entity_id}%",),
            ).fetchall()
        else:
            hold_rows = conn.execute(
                "SELECT * FROM hold_queue ORDER BY created_at DESC"
            ).fetchall()

        holds = []
        for row in hold_rows:
            action_data = json.loads(row["action_json"])
            holds.append({
                "id": row["id"],
                "action": action_data,
                "adjusted_confidence": row["adjusted_confidence"],
                "hold_reason": row["hold_reason"],
                "hold_source": row["hold_source"],
                "verdict": row["verdict"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "resolved": bool(row["resolved"]),
                "resolution": row["resolution"],
            })
        data["holds"] = holds
        record_counts["holds"] = len(holds)
        if holds:
            categories_included.append("holds")

        # 6. Config (excluding system paths and API keys)
        if not entity_id:
            config = self.conductor.config
            config_data = asdict(config)
            for key in EXCLUDED_CONFIG_KEYS:
                config_data.pop(key, None)
            data["config"] = config_data
            categories_included.append("config")

        # 7. Metadata
        data["metadata"] = {
            "export_timestamp": time.time(),
            "export_timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "entity_id": entity_id,
            "data_categories_included": categories_included,
            "record_counts": record_counts,
            "total_records": sum(record_counts.values()),
            "gdpr_version": "1.0",
        }

        return data

    # ------------------------------------------------------------------
    # Export as ZIP
    # ------------------------------------------------------------------

    def export_as_zip(
        self,
        entity_id: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> tuple:
        """Create a ZIP file containing the full export.

        Returns (zip_bytes, output_path_or_none).
        If output_path is provided, writes to disk and returns the Path.
        Otherwise returns the ZIP bytes in memory.
        """
        export_data = self.export_personal_data(entity_id)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # data.json — full export
            zf.writestr("data.json", json.dumps(export_data, default=str, indent=2))

            # README.txt
            readme = self._build_readme(export_data)
            zf.writestr("README.txt", readme)

            # CSV files per category
            if export_data.get("conversations"):
                zf.writestr("conversations.csv", self._to_csv(export_data["conversations"]))

            if export_data.get("entities"):
                zf.writestr("entities.csv", self._to_csv(export_data["entities"]))

            if export_data.get("interactions"):
                zf.writestr("interactions.csv", self._to_csv(export_data["interactions"]))

            if export_data.get("memories"):
                zf.writestr("memories.csv", self._to_csv(export_data["memories"]))

            if export_data.get("holds"):
                # Flatten the action dict for CSV
                flat_holds = []
                for h in export_data["holds"]:
                    row = dict(h)
                    action = row.pop("action", {})
                    row["action_type"] = action.get("action_type", "")
                    row["action_payload"] = json.dumps(action.get("payload", {}))
                    row["action_confidence"] = action.get("confidence", "")
                    row["action_rationale"] = action.get("rationale", "")
                    flat_holds.append(row)
                zf.writestr("holds.csv", self._to_csv(flat_holds))

        zip_bytes = buf.getvalue()

        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(zip_bytes)
            return zip_bytes, p

        return zip_bytes, None

    # ------------------------------------------------------------------
    # Right to erasure
    # ------------------------------------------------------------------

    def delete_personal_data(self, entity_id: str) -> dict:
        """Right to erasure: remove all data related to an entity.

        Returns counts of deleted records per table.
        """
        conn = self.store.conn
        counts: Dict[str, int] = {}

        # Look up entity name for content-based deletion
        entity_row = conn.execute(
            "SELECT name FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if not entity_row:
            return {"error": "Entity not found", "entity_id": entity_id}

        entity_name = entity_row["name"]

        with conn:
            # Delete interactions
            result = conn.execute(
                "DELETE FROM interactions WHERE entity_id = ?", (entity_id,)
            )
            counts["interactions"] = result.rowcount

            # Delete conversations mentioning this entity
            result = conn.execute(
                "DELETE FROM conversations WHERE content LIKE ? OR content LIKE ?",
                (f"%{entity_id}%", f"%{entity_name}%"),
            )
            counts["conversations"] = result.rowcount

            # Delete memories mentioning this entity
            result = conn.execute(
                "DELETE FROM memories WHERE content LIKE ? OR content LIKE ?",
                (f"%{entity_id}%", f"%{entity_name}%"),
            )
            counts["memories"] = result.rowcount

            # Delete hold queue items mentioning this entity
            result = conn.execute(
                "DELETE FROM hold_queue WHERE action_json LIKE ?",
                (f"%{entity_id}%",),
            )
            counts["holds"] = result.rowcount

            # Delete events mentioning this entity
            result = conn.execute(
                "DELETE FROM events WHERE data_json LIKE ? OR data_json LIKE ?",
                (f"%{entity_id}%", f"%{entity_name}%"),
            )
            counts["events"] = result.rowcount

            # Delete the entity itself
            result = conn.execute(
                "DELETE FROM entities WHERE entity_id = ?", (entity_id,)
            )
            counts["entity"] = result.rowcount

        total_deleted = sum(counts.values())

        # Log the deletion event for compliance
        self.store.add_event(
            event_id=str(uuid4()),
            event_type="gdpr_erasure",
            engine="gdpr",
            data={
                "entity_id": entity_id,
                "entity_name": entity_name,
                "deleted_counts": counts,
                "total_deleted": total_deleted,
                "timestamp": time.time(),
            },
        )

        logger.info(
            "GDPR erasure completed for entity %s (%s): %d records deleted",
            entity_id, entity_name, total_deleted,
        )

        return {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "deleted_counts": counts,
            "total_deleted": total_deleted,
            "timestamp": time.time(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_csv(records: List[Dict]) -> str:
        """Convert a list of dicts to a CSV string."""
        if not records:
            return ""
        output = io.StringIO()
        fieldnames = list(records[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)
        return output.getvalue()

    @staticmethod
    def _build_readme(export_data: dict) -> str:
        """Build a README explaining the export data format."""
        meta = export_data.get("metadata", {})
        counts = meta.get("record_counts", {})
        categories = meta.get("data_categories_included", [])

        lines = [
            "HUMANE PERSONAL DATA EXPORT",
            "=" * 40,
            "",
            f"Export Date: {meta.get('export_timestamp_iso', 'unknown')}",
            f"Entity Filter: {meta.get('entity_id') or 'All data (no filter)'}",
            f"GDPR Export Version: {meta.get('gdpr_version', '1.0')}",
            "",
            "DATA CATEGORIES INCLUDED",
            "-" * 40,
        ]
        for cat in categories:
            count = counts.get(cat, 0)
            lines.append(f"  - {cat}: {count} records")

        lines.append(f"\nTotal Records: {meta.get('total_records', 0)}")

        lines.extend([
            "",
            "FILE CONTENTS",
            "-" * 40,
            "  data.json          - Complete export in JSON format",
            "  README.txt         - This file",
            "  conversations.csv  - All conversation messages",
            "  entities.csv       - Entity profiles and relationship data",
            "  interactions.csv   - Interaction history with entities",
            "  memories.csv       - Stored memories",
            "  holds.csv          - Hold queue items and resolutions",
            "",
            "DATA FORMAT NOTES",
            "-" * 40,
            "  - Timestamps are Unix epoch seconds (float)",
            "  - Sentiment scores range from -1.0 (negative) to 1.0 (positive)",
            "  - Trust levels: untrusted, low, neutral, moderate, high, absolute",
            "  - Relationship health: toxic, strained, cooling, stable, warm, close",
            "  - Boolean fields: 0 = false, 1 = true",
            "",
            "YOUR RIGHTS UNDER GDPR",
            "-" * 40,
            "  - Right of Access (Art. 15): This export fulfills your right to access",
            "    all personal data processed about you.",
            "  - Right to Erasure (Art. 17): You may request deletion of all your",
            "    personal data through the application's settings page.",
            "  - Right to Portability (Art. 20): This export is provided in",
            "    machine-readable formats (JSON, CSV) for data portability.",
            "",
        ])
        return "\n".join(lines)
