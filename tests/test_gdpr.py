"""Tests for the GDPRExporter — personal data export and erasure."""

import json
import time
import zipfile
import io
import pytest
from uuid import uuid4

from humane.core.config import HumaneConfig
from humane.core.models import EntityState, EntityType, Memory, MemoryType
from humane.core.store import Store
from humane.gdpr import GDPRExporter


@pytest.fixture
def config():
    return HumaneConfig()


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_gdpr.db")
    store = Store(db_path)
    store.initialize()
    return store


@pytest.fixture
def conductor_mock(config):
    from unittest.mock import MagicMock
    conductor = MagicMock()
    conductor.config = config
    return conductor


@pytest.fixture
def exporter(tmp_db, conductor_mock):
    return GDPRExporter(tmp_db, conductor_mock)


def _seed_entity(store, entity_id="ent1", name="Alice"):
    entity = EntityState(
        entity_id=entity_id, name=name,
        entity_type=EntityType.CLIENT,
        sentiment_score=0.5,
        created_at=time.time() - 86400,
    )
    store.add_entity(entity)
    return entity_id


def _seed_conversation(store, entity_id="ent1", entity_name="Alice"):
    cid = str(uuid4())
    store.add_conversation(
        conversation_id=cid, chat_id=1, user_id=1,
        role="user", content=f"Message about {entity_name} and {entity_id}",
        sentiment=0.3,
    )
    return cid


def _seed_interaction(store, entity_id="ent1"):
    iid = str(uuid4())
    store.add_interaction(
        interaction_id=iid, entity_id=entity_id,
        sentiment=0.5, content_summary="Test interaction",
    )
    return iid


def _seed_memory(store, entity_name="Alice"):
    mid = str(uuid4())
    mem = Memory(
        id=mid, memory_type=MemoryType.EPISODIC,
        content=f"Meeting with {entity_name} about the project",
        relevance_score=0.8,
    )
    store.add_memory(mem)
    return mid


class TestExportPersonalData:
    def test_export_includes_all_categories(self, exporter, tmp_db):
        _seed_entity(tmp_db)
        _seed_conversation(tmp_db)
        _seed_interaction(tmp_db)
        _seed_memory(tmp_db)

        data = exporter.export_personal_data()
        assert "conversations" in data
        assert "entities" in data
        assert "interactions" in data
        assert "memories" in data
        assert "holds" in data
        assert "metadata" in data

    def test_export_metadata_has_counts(self, exporter, tmp_db):
        _seed_entity(tmp_db)
        _seed_conversation(tmp_db)

        data = exporter.export_personal_data()
        meta = data["metadata"]
        assert "record_counts" in meta
        assert "total_records" in meta
        assert "data_categories_included" in meta
        assert meta["total_records"] > 0

    def test_export_includes_config_for_full_export(self, exporter, tmp_db):
        _seed_entity(tmp_db)
        data = exporter.export_personal_data()
        assert "config" in data

    def test_export_excludes_config_for_entity_export(self, exporter, tmp_db):
        eid = _seed_entity(tmp_db)
        data = exporter.export_personal_data(entity_id=eid)
        assert "config" not in data


class TestExportForSpecificEntity:
    def test_export_filtered_by_entity(self, exporter, tmp_db):
        eid = _seed_entity(tmp_db, "ent1", "Alice")
        _seed_entity(tmp_db, "ent2", "Bob")
        _seed_conversation(tmp_db, "ent1", "Alice")
        _seed_interaction(tmp_db, "ent1")

        data = exporter.export_personal_data(entity_id="ent1")
        assert len(data["entities"]) == 1
        assert data["entities"][0]["entity_id"] == "ent1"


class TestDeletePersonalData:
    def test_delete_removes_entity_data(self, exporter, tmp_db):
        eid = _seed_entity(tmp_db, "ent_del", "DeleteMe")
        _seed_conversation(tmp_db, "ent_del", "DeleteMe")
        _seed_interaction(tmp_db, "ent_del")

        result = exporter.delete_personal_data("ent_del")
        assert "deleted_counts" in result
        assert result["total_deleted"] > 0
        assert result["entity_id"] == "ent_del"

        # Verify entity is gone
        entity = tmp_db.get_entity("ent_del")
        assert entity is None

    def test_delete_nonexistent_entity_returns_error(self, exporter):
        result = exporter.delete_personal_data("nonexistent")
        assert "error" in result


class TestExportAsZip:
    def test_export_as_zip_creates_valid_zip(self, exporter, tmp_db):
        _seed_entity(tmp_db)
        _seed_conversation(tmp_db)

        zip_bytes, _ = exporter.export_as_zip()
        assert len(zip_bytes) > 0

        # Verify it's a valid ZIP
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
            assert "data.json" in names
            assert "README.txt" in names

    def test_export_as_zip_contains_csv_files(self, exporter, tmp_db):
        _seed_entity(tmp_db)
        _seed_conversation(tmp_db)
        _seed_interaction(tmp_db)

        zip_bytes, _ = exporter.export_as_zip()
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
            assert "conversations.csv" in names
            assert "entities.csv" in names
            assert "interactions.csv" in names

    def test_export_as_zip_to_disk(self, exporter, tmp_db, tmp_path):
        _seed_entity(tmp_db)
        out_path = str(tmp_path / "export.zip")
        zip_bytes, path = exporter.export_as_zip(output_path=out_path)
        assert path is not None
        assert path.exists()
        assert len(zip_bytes) > 0


class TestDataCountsInExportMetadata:
    def test_data_counts_accurate(self, exporter, tmp_db):
        _seed_entity(tmp_db, "e1", "Alice")
        _seed_entity(tmp_db, "e2", "Bob")
        _seed_conversation(tmp_db)
        _seed_conversation(tmp_db)
        _seed_conversation(tmp_db)
        _seed_interaction(tmp_db, "e1")

        data = exporter.export_personal_data()
        counts = data["metadata"]["record_counts"]
        assert counts["entities"] == 2
        assert counts["conversations"] == 3
        assert counts["interactions"] == 1
