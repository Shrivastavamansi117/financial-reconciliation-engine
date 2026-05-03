"""
test_reconciler.py
------------------
Unit tests for every mismatch scenario.

Run with:  python -m pytest tests/test_reconciler.py -v
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

# Make src importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_generator import generate_datasets
from reconciler import Reconciler


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _make_txn(txn_id, amount, txn_date="2024-01-10", status="captured", edge_case=None):
    return {
        "txn_id": txn_id,
        "merchant": "Test Corp",
        "txn_date": pd.Timestamp(txn_date),
        "amount": Decimal(str(amount)),
        "status": status,
        "edge_case": edge_case,
    }


def _make_set(settlement_id, txn_id, amount, settlement_date, edge_case=None):
    return {
        "settlement_id": settlement_id,
        "txn_id": txn_id,
        "settlement_date": pd.Timestamp(settlement_date),
        "settled_amount": Decimal(str(amount)),
        "edge_case": edge_case,
    }


def _run(txns, sets):
    t = pd.DataFrame(txns)
    s = pd.DataFrame(sets)
    r = Reconciler(t, s)
    r.run()
    return r


# ─── Test: Fully matched ────────────────────────────────────────────────────────

class TestMatched:
    def test_single_match(self):
        txns = [_make_txn("T001", "100.00")]
        sets = [_make_set("S001", "T001", "100.00", "2024-01-11")]
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "matched"

    def test_match_rate_100_pct(self):
        txns = [_make_txn(f"T{i:03d}", "50.00") for i in range(5)]
        sets = [_make_set(f"S{i:03d}", f"T{i:03d}", "50.00", "2024-01-11") for i in range(5)]
        r = _run(txns, sets)
        assert r.aggregate_totals()["match_rate_pct"] == 100.0


# ─── Test: Missing settlement ───────────────────────────────────────────────────

class TestMissingSettlement:
    def test_classified_correctly(self):
        txns = [_make_txn("T001", "200.00")]
        sets = []  # no settlement
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "missing_settlement"

    def test_impact_equals_txn_amount(self):
        txns = [_make_txn("T001", "300.00")]
        r = _run(txns, [])
        detail = r.details()
        # impact = -txn_amount (revenue not yet received)
        assert detail.iloc[0]["amount_diff"] == pytest.approx(-300.00, abs=0.01)

    def test_count_in_summary(self):
        txns = [_make_txn(f"T{i}", "100.00") for i in range(3)]
        r = _run(txns, [])
        summary = r.summary()
        row = summary[summary["issue"] == "missing_settlement"]
        assert row["count"].iloc[0] == 3


# ─── Test: Delayed settlement ───────────────────────────────────────────────────

class TestDelayedSettlement:
    def test_3_business_days_is_delayed(self):
        # Jan 10 (Wed) → Jan 15 (Mon) = 3 business days (Thu, Fri, Mon)
        txns = [_make_txn("T001", "150.00", txn_date="2024-01-10")]
        sets = [_make_set("S001", "T001", "150.00", "2024-01-15")]
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "delayed_settlement"

    def test_2_business_days_is_normal(self):
        # Jan 10 (Wed) → Jan 12 (Fri) = 2 business days
        txns = [_make_txn("T001", "150.00", txn_date="2024-01-10")]
        sets = [_make_set("S001", "T001", "150.00", "2024-01-12")]
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "matched"


# ─── Test: Timing mismatch ──────────────────────────────────────────────────────

class TestTimingMismatch:
    def test_next_month_settlement(self):
        txns = [_make_txn("T001", "500.00", txn_date="2024-01-28")]
        sets = [_make_set("S001", "T001", "500.00", "2024-02-05")]
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "timing_mismatch"

    def test_same_month_is_not_flagged(self):
        txns = [_make_txn("T001", "500.00", txn_date="2024-01-05")]
        sets = [_make_set("S001", "T001", "500.00", "2024-01-07")]
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "matched"


# ─── Test: Amount mismatch / Rounding ──────────────────────────────────────────

class TestAmountMismatch:
    def test_penny_rounding_flagged(self):
        txns = [_make_txn("T001", "99.99")]
        sets = [_make_set("S001", "T001", "99.98", "2024-01-11")]  # $0.01 diff
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "amount_mismatch"
        assert detail.iloc[0]["amount_diff"] == pytest.approx(-0.01, abs=0.001)

    def test_aggregate_rounding_impact_compounds(self):
        """10 × $0.01 rounding diff should total $0.10 impact."""
        txns = [_make_txn(f"T{i:03d}", "100.00") for i in range(10)]
        sets = [_make_set(f"S{i:03d}", f"T{i:03d}", "99.99", "2024-01-11") for i in range(10)]
        r = _run(txns, sets)
        summary = r.summary()
        row = summary[summary["issue"] == "amount_mismatch"]
        assert abs(row["total_impact"].iloc[0]) == pytest.approx(0.10, abs=0.001)

    def test_exact_match_not_flagged(self):
        txns = [_make_txn("T001", "250.00")]
        sets = [_make_set("S001", "T001", "250.00", "2024-01-11")]
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "matched"


# ─── Test: Duplicate records ────────────────────────────────────────────────────

class TestDuplicateRecords:
    def test_duplicate_settlement_detected(self):
        txns = [_make_txn("T001", "400.00")]
        sets = [
            _make_set("S001a", "T001", "400.00", "2024-01-11"),
            _make_set("S001b", "T001", "400.00", "2024-01-11"),  # duplicate
        ]
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] == "duplicate"

    def test_single_settlement_not_flagged(self):
        txns = [_make_txn("T001", "400.00")]
        sets = [_make_set("S001", "T001", "400.00", "2024-01-11")]
        r = _run(txns, sets)
        detail = r.details()
        assert detail.iloc[0]["issue"] != "duplicate"


# ─── Test: Orphan refund ────────────────────────────────────────────────────────

class TestOrphanRefund:
    def test_negative_amount_no_settlement_is_orphan(self):
        txns = [_make_txn("T001", "-75.00", status="refunded")]
        r = _run(txns, [])
        detail = r.details()
        assert detail.iloc[0]["issue"] == "orphan_refund"

    def test_positive_amount_no_settlement_is_missing(self):
        txns = [_make_txn("T001", "75.00")]
        r = _run(txns, [])
        detail = r.details()
        assert detail.iloc[0]["issue"] == "missing_settlement"


# ─── Integration test: full synthetic dataset ───────────────────────────────────

class TestIntegration:
    def setup_method(self):
        txns, sets = generate_datasets()
        self.r = Reconciler(txns, sets).run()

    def test_all_issue_types_present(self):
        summary = self.r.summary()
        found_issues = set(summary["issue"].tolist())
        expected = {
            "matched",
            "duplicate",
            "orphan_refund",
            "missing_settlement",
            "timing_mismatch",
            "amount_mismatch",
        }
        assert expected.issubset(found_issues), (
            f"Missing issue types: {expected - found_issues}"
        )

    def test_match_rate_above_75_pct(self):
        totals = self.r.aggregate_totals()
        assert totals["match_rate_pct"] >= 75.0

    def test_no_null_txn_ids_in_details(self):
        detail = self.r.details()
        assert detail["txn_id"].notna().all()

    def test_summary_counts_sum_to_total(self):
        total = self.r.aggregate_totals()["total_transactions"]
        summary_total = self.r.summary()["count"].sum()
        assert total == summary_total


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
