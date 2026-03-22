"""Conversation Categorizer — keyword-based auto-tagging for conversations."""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional


# Category keyword maps: category -> list of trigger words
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "sales": [
        "deal", "proposal", "quote", "pricing", "contract", "close",
        "prospect", "revenue", "pipeline",
    ],
    "support": [
        "help", "issue", "bug", "fix", "problem", "error", "broken",
        "ticket", "urgent",
    ],
    "personal": [
        "lunch", "coffee", "birthday", "vacation", "family", "weekend",
        "holiday",
    ],
    "operations": [
        "deadline", "schedule", "meeting", "review", "status", "update",
        "progress", "milestone",
    ],
    "finance": [
        "invoice", "payment", "budget", "expense", "cost", "billing",
        "receipt",
    ],
    "hiring": [
        "candidate", "interview", "resume", "hire", "position", "role",
        "onboard",
    ],
}


class ConversationCategorizer:
    """Score text against keyword categories and return the best match."""

    def __init__(self, keywords: Optional[Dict[str, List[str]]] = None):
        self.keywords = keywords or CATEGORY_KEYWORDS

    def categorize(self, text: str) -> str:
        """Return the single best category tag for *text*.

        Scores each category by counting keyword hits in the lowercased text.
        Returns ``"general"`` when no category scores above zero.
        """
        if not text:
            return "general"

        text_lower = text.lower()
        words = set(text_lower.split())

        scores: Dict[str, int] = {}
        for category, kws in self.keywords.items():
            score = 0
            for kw in kws:
                # Check both whole-word membership and substring presence
                # so that "pricing" matches even inside a compound token.
                if kw in words or kw in text_lower:
                    score += 1
            if score > 0:
                scores[category] = score

        if not scores:
            return "general"

        # Pick highest score; ties broken by dict insertion order (stable).
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def categorize_batch(self, messages: List[str]) -> Dict[str, str]:
        """Categorize multiple messages and return the dominant category.

        Returns a dict with:
        - ``"dominant"``: the most common category across all messages
        - ``"distribution"``: ``{category: count}`` mapping
        - ``"per_message"``: list of per-message categories (same order)
        """
        if not messages:
            return {"dominant": "general", "distribution": {}, "per_message": []}

        categories = [self.categorize(msg) for msg in messages]
        counts = Counter(categories)
        dominant = counts.most_common(1)[0][0]

        return {
            "dominant": dominant,
            "distribution": dict(counts),
            "per_message": categories,
        }
