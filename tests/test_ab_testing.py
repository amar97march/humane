"""Tests for the ABTestManager — A/B personality testing system."""

import pytest

from humane.ab_testing import ABTestManager
from humane.core.store import Store


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_ab.db")
    store = Store(db_path)
    store.initialize()
    return store


@pytest.fixture
def ab_manager(tmp_db):
    return ABTestManager(tmp_db)


class TestCreateTest:
    def test_create_test_returns_test_id(self, ab_manager):
        test_id = ab_manager.create_test(
            name="Tone test",
            personality_a="formal",
            personality_b="casual",
        )
        assert isinstance(test_id, str)
        assert len(test_id) > 0

    def test_created_test_appears_in_list(self, ab_manager):
        test_id = ab_manager.create_test("Test1", "A-style", "B-style")
        tests = ab_manager.list_tests()
        assert len(tests) == 1
        assert tests[0]["id"] == test_id
        assert tests[0]["status"] == "active"


class TestAssignVariant:
    def test_assign_variant_returns_a_or_b(self, ab_manager):
        test_id = ab_manager.create_test("Test", "A", "B")
        variant = ab_manager.assign_variant(test_id, chat_id=12345)
        assert variant in ("A", "B")

    def test_sticky_assignment(self, ab_manager):
        test_id = ab_manager.create_test("Test", "A", "B")
        variant1 = ab_manager.assign_variant(test_id, chat_id=99999)
        variant2 = ab_manager.assign_variant(test_id, chat_id=99999)
        variant3 = ab_manager.assign_variant(test_id, chat_id=99999)
        assert variant1 == variant2 == variant3

    def test_different_chats_can_get_different_variants(self, ab_manager):
        test_id = ab_manager.create_test("Test", "A", "B")
        variants = set()
        # Try many chat IDs to get both variants
        for i in range(100):
            v = ab_manager.assign_variant(test_id, chat_id=i)
            variants.add(v)
        assert "A" in variants
        assert "B" in variants


class TestRecordResult:
    def test_record_result_stores_data(self, ab_manager):
        test_id = ab_manager.create_test("Test", "A", "B")
        ab_manager.assign_variant(test_id, chat_id=100)
        ab_manager.record_result(test_id, chat_id=100, metric="sentiment", value=0.8)

        results = ab_manager.get_results(test_id)
        assert "variants" in results
        # At least one variant should have data
        total_counts = 0
        for variant_data in results["variants"].values():
            if "sentiment" in variant_data:
                total_counts += variant_data["sentiment"]["count"]
        assert total_counts >= 1


class TestGetResults:
    def test_get_results_aggregates_correctly(self, ab_manager):
        test_id = ab_manager.create_test("Test", "A", "B")
        # Record multiple results
        for chat_id in range(10):
            ab_manager.assign_variant(test_id, chat_id=chat_id)
            ab_manager.record_result(test_id, chat_id=chat_id, metric="satisfaction", value=0.5 + chat_id * 0.05)

        results = ab_manager.get_results(test_id)
        assert results["test"]["id"] == test_id
        assert "variants" in results
        assert "A" in results["variants"]
        assert "B" in results["variants"]

    def test_get_results_nonexistent_test(self, ab_manager):
        results = ab_manager.get_results("nonexistent-id")
        assert "error" in results


class TestEndTest:
    def test_end_test_marks_winner(self, ab_manager):
        test_id = ab_manager.create_test("Test", "A", "B")
        ab_manager.end_test(test_id, winner="A")

        tests = ab_manager.list_tests()
        ended = [t for t in tests if t["id"] == test_id][0]
        assert ended["status"] == "ended"
        assert ended["winner"] == "A"
        assert ended["end_time"] is not None

    def test_end_test_without_winner(self, ab_manager):
        test_id = ab_manager.create_test("Test", "A", "B")
        ab_manager.end_test(test_id)

        tests = ab_manager.list_tests()
        ended = [t for t in tests if t["id"] == test_id][0]
        assert ended["status"] == "ended"
        assert ended["winner"] is None


class TestActiveTestForChat:
    def test_get_active_test_for_chat(self, ab_manager):
        test_id = ab_manager.create_test("Active Test", "Formal", "Casual")
        result = ab_manager.get_active_test_for_chat(chat_id=555)
        assert result is not None
        assert result["test_id"] == test_id
        assert result["variant"] in ("A", "B")
        assert result["personality"] in ("Formal", "Casual")

    def test_no_active_test(self, ab_manager):
        result = ab_manager.get_active_test_for_chat(chat_id=555)
        assert result is None
