"""Tests for the ConversationCategorizer — keyword-based message tagging."""

import pytest

from humane.categorizer import ConversationCategorizer


@pytest.fixture
def categorizer():
    return ConversationCategorizer()


class TestCategorize:
    def test_returns_valid_category_string(self, categorizer):
        result = categorizer.categorize("Can you send me the proposal?")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_sales_keywords_detected(self, categorizer):
        assert categorizer.categorize("Let's close the deal and send the pricing") == "sales"

    def test_support_keywords_detected(self, categorizer):
        assert categorizer.categorize("I have a bug and need help fixing this issue") == "support"

    def test_personal_keywords_detected(self, categorizer):
        assert categorizer.categorize("Let's grab lunch and coffee this weekend") == "personal"

    def test_operations_keywords_detected(self, categorizer):
        assert categorizer.categorize("Schedule a meeting to review the deadline status") == "operations"

    def test_finance_keywords_detected(self, categorizer):
        assert categorizer.categorize("Please send the invoice for the payment") == "finance"

    def test_default_to_general_for_ambiguous(self, categorizer):
        assert categorizer.categorize("Hello there, how are you today?") == "general"

    def test_empty_string_returns_general(self, categorizer):
        assert categorizer.categorize("") == "general"


class TestCategorizeBatch:
    def test_batch_returns_expected_structure(self, categorizer):
        messages = [
            "Send the proposal and pricing",
            "I have a bug to fix",
            "Let's grab coffee",
        ]
        result = categorizer.categorize_batch(messages)
        assert "dominant" in result
        assert "distribution" in result
        assert "per_message" in result
        assert len(result["per_message"]) == 3

    def test_batch_dominant_category(self, categorizer):
        messages = [
            "Close the deal",
            "Send the pricing",
            "Proposal review",
            "Weekend plans",
        ]
        result = categorizer.categorize_batch(messages)
        assert result["dominant"] == "sales"

    def test_empty_batch_returns_general(self, categorizer):
        result = categorizer.categorize_batch([])
        assert result["dominant"] == "general"
        assert result["per_message"] == []


class TestMixedCategory:
    def test_mixed_picks_strongest(self, categorizer):
        # More sales keywords than support keywords
        text = "The deal proposal pricing for the fix"
        result = categorizer.categorize(text)
        # "deal", "proposal", "pricing" = 3 sales; "fix" = 1 support
        assert result == "sales"

    def test_custom_keywords(self):
        custom = {"engineering": ["code", "deploy", "build", "test"]}
        cat = ConversationCategorizer(keywords=custom)
        assert cat.categorize("Let's deploy the build") == "engineering"
        assert cat.categorize("Hello world") == "general"
