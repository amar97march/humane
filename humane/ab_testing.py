"""A/B personality testing system for Humane.

Allows running split tests between two personality variants to measure
which conversation style produces better outcomes.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from humane.core.store import Store


@dataclass
class ABTest:
    """A single A/B test comparing two personality variants."""

    id: str
    name: str
    personality_a: str
    personality_b: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "active"  # active | ended
    winner: Optional[str] = None  # "A", "B", or None


class ABTestManager:
    """Manages A/B personality tests with sticky variant assignment and result tracking."""

    def __init__(self, store: Store):
        self.store = store
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create ab_tests and ab_results tables if they don't exist."""
        with self.store.conn:
            self.store.conn.executescript("""
                CREATE TABLE IF NOT EXISTS ab_tests (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    personality_a TEXT NOT NULL,
                    personality_b TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    status TEXT NOT NULL DEFAULT 'active',
                    winner TEXT
                );

                CREATE TABLE IF NOT EXISTS ab_results (
                    id TEXT PRIMARY KEY,
                    test_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    variant TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (test_id) REFERENCES ab_tests(id)
                );

                CREATE INDEX IF NOT EXISTS idx_ab_results_test
                    ON ab_results(test_id, variant);

                CREATE TABLE IF NOT EXISTS ab_assignments (
                    test_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    variant TEXT NOT NULL,
                    assigned_at REAL NOT NULL,
                    PRIMARY KEY (test_id, chat_id),
                    FOREIGN KEY (test_id) REFERENCES ab_tests(id)
                );
            """)

    def create_test(self, name: str, personality_a: str, personality_b: str) -> str:
        """Create a new A/B test. Returns test_id."""
        test_id = str(uuid4())
        now = time.time()
        with self.store.conn:
            self.store.conn.execute(
                """INSERT INTO ab_tests (id, name, personality_a, personality_b, start_time, status)
                   VALUES (?, ?, ?, ?, ?, 'active')""",
                (test_id, name, personality_a, personality_b, now),
            )
        return test_id

    def assign_variant(self, test_id: str, chat_id: int) -> str:
        """Assign a variant to a chat_id for a given test. Sticky — same chat always gets same variant.

        Returns "A" or "B".
        """
        # Check for existing assignment
        row = self.store.conn.execute(
            "SELECT variant FROM ab_assignments WHERE test_id = ? AND chat_id = ?",
            (test_id, chat_id),
        ).fetchone()
        if row:
            return row["variant"]

        # Deterministic 50/50 split based on hash of test_id + chat_id
        hash_input = f"{test_id}:{chat_id}".encode()
        hash_val = int(hashlib.sha256(hash_input).hexdigest(), 16)
        variant = "A" if hash_val % 2 == 0 else "B"

        with self.store.conn:
            self.store.conn.execute(
                """INSERT OR IGNORE INTO ab_assignments (test_id, chat_id, variant, assigned_at)
                   VALUES (?, ?, ?, ?)""",
                (test_id, chat_id, variant, time.time()),
            )
        return variant

    def record_result(self, test_id: str, chat_id: int, metric: str, value: float) -> None:
        """Record a metric result for a chat in a test.

        Metrics: response_sentiment, approval_rate, user_satisfaction
        """
        variant = self.assign_variant(test_id, chat_id)
        result_id = str(uuid4())
        with self.store.conn:
            self.store.conn.execute(
                """INSERT INTO ab_results (id, test_id, chat_id, variant, metric, value, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (result_id, test_id, chat_id, variant, metric, value, time.time()),
            )

    def get_results(self, test_id: str) -> Dict[str, Any]:
        """Get aggregated results for a test with statistical significance.

        Returns per-variant: avg sentiment, approval rate, sample size, and z-test significance.
        """
        test = self._get_test(test_id)
        if not test:
            return {"error": "Test not found"}

        results: Dict[str, Any] = {
            "test": test,
            "variants": {"A": {}, "B": {}},
        }

        for variant in ("A", "B"):
            # Get all results for this variant
            rows = self.store.conn.execute(
                "SELECT metric, value FROM ab_results WHERE test_id = ? AND variant = ?",
                (test_id, variant),
            ).fetchall()

            # Group by metric
            metrics: Dict[str, List[float]] = {}
            for row in rows:
                m = row["metric"]
                if m not in metrics:
                    metrics[m] = []
                metrics[m].append(row["value"])

            # Compute per-metric stats
            metric_stats: Dict[str, Any] = {}
            for m, values in metrics.items():
                n = len(values)
                avg = sum(values) / n if n > 0 else 0.0
                metric_stats[m] = {
                    "avg": round(avg, 4),
                    "count": n,
                }
            results["variants"][variant] = metric_stats

            # Count unique chats assigned to this variant
            chat_count = self.store.conn.execute(
                "SELECT COUNT(DISTINCT chat_id) as cnt FROM ab_assignments WHERE test_id = ? AND variant = ?",
                (test_id, variant),
            ).fetchone()
            results["variants"][variant]["_sample_size"] = chat_count["cnt"] if chat_count else 0

        # Statistical significance (z-test) for each shared metric
        significance: Dict[str, Any] = {}
        a_metrics = results["variants"]["A"]
        b_metrics = results["variants"]["B"]
        shared_metrics = set(k for k in a_metrics if not k.startswith("_")) & set(
            k for k in b_metrics if not k.startswith("_")
        )

        for m in shared_metrics:
            a_data = a_metrics[m]
            b_data = b_metrics[m]
            sig = self._z_test(test_id, m)
            significance[m] = sig

        results["significance"] = significance
        return results

    def _z_test(self, test_id: str, metric: str) -> Dict[str, Any]:
        """Basic two-proportion z-test for a metric between variants A and B."""
        stats: Dict[str, Dict[str, float]] = {}
        for variant in ("A", "B"):
            rows = self.store.conn.execute(
                "SELECT value FROM ab_results WHERE test_id = ? AND variant = ? AND metric = ?",
                (test_id, variant, metric),
            ).fetchall()
            values = [r["value"] for r in rows]
            n = len(values)
            if n == 0:
                stats[variant] = {"mean": 0.0, "std": 0.0, "n": 0}
                continue
            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
            std = math.sqrt(variance)
            stats[variant] = {"mean": mean, "std": std, "n": n}

        n_a = stats["A"]["n"]
        n_b = stats["B"]["n"]

        if n_a < 2 or n_b < 2:
            return {
                "z_score": 0.0,
                "p_value": 1.0,
                "significant": False,
                "message": "Insufficient data for significance test",
            }

        mean_a, std_a = stats["A"]["mean"], stats["A"]["std"]
        mean_b, std_b = stats["B"]["mean"], stats["B"]["std"]

        # Pooled standard error
        se = math.sqrt((std_a**2 / n_a) + (std_b**2 / n_b))
        if se == 0:
            return {
                "z_score": 0.0,
                "p_value": 1.0,
                "significant": False,
                "message": "No variance in data",
            }

        z = (mean_a - mean_b) / se

        # Approximate p-value using normal CDF (two-tailed)
        p_value = 2 * (1 - self._normal_cdf(abs(z)))

        return {
            "z_score": round(z, 4),
            "p_value": round(p_value, 4),
            "significant": p_value < 0.05,
            "leading": "A" if mean_a > mean_b else "B" if mean_b > mean_a else "tie",
        }

    @staticmethod
    def _normal_cdf(x: float) -> float:
        """Approximate standard normal CDF using error function approximation."""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def list_tests(self) -> List[Dict[str, Any]]:
        """List all A/B tests."""
        rows = self.store.conn.execute(
            "SELECT * FROM ab_tests ORDER BY start_time DESC"
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def end_test(self, test_id: str, winner: Optional[str] = None) -> None:
        """End an A/B test, optionally declaring a winner."""
        with self.store.conn:
            self.store.conn.execute(
                "UPDATE ab_tests SET status = 'ended', end_time = ?, winner = ? WHERE id = ?",
                (time.time(), winner, test_id),
            )

    def get_active_test_for_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Get the active A/B test and assigned variant for a chat, if any.

        Returns dict with test info and variant, or None.
        """
        row = self.store.conn.execute(
            "SELECT * FROM ab_tests WHERE status = 'active' ORDER BY start_time DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None

        test = self._row_to_dict(row)
        variant = self.assign_variant(test["id"], chat_id)
        personality = test["personality_a"] if variant == "A" else test["personality_b"]
        return {
            "test_id": test["id"],
            "test_name": test["name"],
            "variant": variant,
            "personality": personality,
        }

    def _get_test(self, test_id: str) -> Optional[Dict[str, Any]]:
        row = self.store.conn.execute(
            "SELECT * FROM ab_tests WHERE id = ?", (test_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "personality_a": row["personality_a"],
            "personality_b": row["personality_b"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "status": row["status"],
            "winner": row["winner"],
        }
