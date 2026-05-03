"""
reconciler.py
-------------
Matches transactions against settlements and classifies each mismatch.

Classification priority (applied in order):
  1. duplicate          – txn_id appears >1 time in settlements
  2. orphan_refund      – transaction amount is negative, no settlement
  3. missing_settlement – no settlement found for a captured transaction
  4. delayed_settlement – settlement exists but >2 business days later
  5. timing_mismatch    – settlement falls in a different calendar month
  6. amount_mismatch    – matched but settled_amount ≠ transaction amount
  7. matched            – fully reconciled ✓

Assumptions:
  - Primary match key: txn_id
  - "Delayed" = settlement_date more than 2 business days after txn_date
  - "Timing mismatch" = settlement month ≠ transaction month (supersedes delayed)
  - Amount tolerance for "matched": exactly $0.00 (any diff → amount_mismatch)
  - Rounding diffs ARE classified as amount_mismatch (intentional: they matter at scale)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

import pandas as pd

# ─── Constants ─────────────────────────────────────────────────────────────────

NORMAL_SETTLE_DAYS = 2          # business days
AMOUNT_TOLERANCE = Decimal("0.00")  # strict; change to 0.02 to ignore penny diffs

ISSUE_LABELS = {
    "matched": "✅ Matched",
    "duplicate": "🔁 Duplicate Record",
    "orphan_refund": "↩️ Orphan Refund",
    "missing_settlement": "❌ Missing Settlement",
    "delayed_settlement": "⏳ Delayed Settlement",
    "timing_mismatch": "📅 Timing Mismatch (Next Month)",
    "amount_mismatch": "💲 Amount Mismatch",
}


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _business_days_between(start, end) -> int:
    """Count business days between two dates (exclusive of start, inclusive of end)."""
    if end <= start:
        return 0
    count = 0
    current = start
    while current < end:
        current = current + pd.Timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return count


def _different_month(d1, d2) -> bool:
    return (d1.year, d1.month) != (d2.year, d2.month)


# ─── Main reconciler ───────────────────────────────────────────────────────────

class Reconciler:
    """
    Stateful reconciliation engine.

    Usage:
        r = Reconciler(transactions_df, settlements_df)
        r.run()
        summary = r.summary()
        details = r.details()
    """

    def __init__(self, transactions: pd.DataFrame, settlements: pd.DataFrame):
        self.txn = transactions.copy()
        self.set = settlements.copy()
        self._results: List[dict] = []
        self._ran = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self) -> "Reconciler":
        """Execute the full reconciliation pipeline."""
        self._results = []
        self._reconcile()
        self._ran = True
        return self

    def summary(self) -> pd.DataFrame:
        """Aggregate summary: one row per issue type."""
        if not self._ran:
            raise RuntimeError("Call .run() first.")
        df = pd.DataFrame(self._results)
        grp = (
            df.groupby("issue")
            .agg(
                count=("txn_id", "count"),
                total_txn_amount=("txn_amount", "sum"),
                total_impact=("amount_diff", "sum"),
            )
            .reset_index()
        )
        grp["issue_label"] = grp["issue"].map(ISSUE_LABELS)
        grp["total_impact"] = grp["total_impact"].apply(
            lambda x: round(float(x), 2)
        )
        grp["total_txn_amount"] = grp["total_txn_amount"].apply(
            lambda x: round(float(x), 2)
        )
        return grp[["issue_label", "issue", "count", "total_txn_amount", "total_impact"]]

    def details(self) -> pd.DataFrame:
        """Row-level detail for every transaction."""
        if not self._ran:
            raise RuntimeError("Call .run() first.")
        df = pd.DataFrame(self._results)
        df["txn_amount"] = df["txn_amount"].apply(lambda x: round(float(x), 2))
        df["settled_amount"] = df["settled_amount"].apply(
            lambda x: round(float(x), 2) if x is not None else None
        )
        df["amount_diff"] = df["amount_diff"].apply(lambda x: round(float(x), 2))
        df["issue_label"] = df["issue"].map(ISSUE_LABELS)
        return df

    # ── Internal pipeline ──────────────────────────────────────────────────────

    def _reconcile(self):
        # Step 1: detect duplicate txn_ids in settlements
        dup_txn_ids = set(
            self.set[self.set.duplicated(subset="txn_id", keep=False)]["txn_id"]
        )

        # Step 2: build a lookup: txn_id → first (or only) settlement row
        settle_lookup: Dict[str, dict] = {}
        for _, row in self.set.iterrows():
            tid = row["txn_id"]
            if tid not in settle_lookup:
                settle_lookup[tid] = row.to_dict()

        # Step 3: iterate every transaction and classify
        for _, txn_row in self.txn.iterrows():
            tid = txn_row["txn_id"]
            txn_amount = Decimal(str(txn_row["amount"]))
            txn_date = pd.Timestamp(txn_row["txn_date"])
            is_refund = txn_amount < 0

            result = {
                "txn_id": tid,
                "merchant": txn_row["merchant"],
                "txn_date": txn_date.date(),
                "txn_amount": txn_amount,
                "settlement_id": None,
                "settlement_date": None,
                "settled_amount": None,
                "amount_diff": Decimal("0"),
                "business_days_to_settle": None,
                "issue": "matched",
                "edge_case_label": txn_row.get("edge_case"),
            }

            # ── Priority 1: Duplicate in settlements ──────────────────────────
            if tid in dup_txn_ids:
                result["issue"] = "duplicate"
                # record the settled amount from first row
                sr = settle_lookup.get(tid)
                if sr:
                    result["settlement_id"] = sr["settlement_id"]
                    result["settled_amount"] = Decimal(str(sr["settled_amount"]))
                    result["amount_diff"] = result["settled_amount"] - txn_amount
                self._results.append(result)
                continue

            # ── Priority 2: Orphan refund (no settlement expected) ────────────
            if is_refund and tid not in settle_lookup:
                result["issue"] = "orphan_refund"
                result["amount_diff"] = txn_amount  # full refund = full impact
                self._results.append(result)
                continue

            # ── Priority 3: Missing settlement ────────────────────────────────
            if tid not in settle_lookup:
                result["issue"] = "missing_settlement"
                result["amount_diff"] = -txn_amount  # lost revenue
                self._results.append(result)
                continue

            # ── Matched: enrich with settlement data ──────────────────────────
            sr = settle_lookup[tid]
            settled_amount = Decimal(str(sr["settled_amount"]))
            settle_date = pd.Timestamp(sr["settlement_date"])
            bdays = _business_days_between(txn_date, settle_date)

            result.update({
                "settlement_id": sr["settlement_id"],
                "settlement_date": settle_date.date(),
                "settled_amount": settled_amount,
                "amount_diff": settled_amount - txn_amount,
                "business_days_to_settle": bdays,
            })

            # ── Priority 4: Timing mismatch (next month) ──────────────────────
            if _different_month(txn_date, settle_date):
                result["issue"] = "timing_mismatch"

            # ── Priority 5: Delayed settlement ────────────────────────────────
            elif bdays > NORMAL_SETTLE_DAYS:
                result["issue"] = "delayed_settlement"

            # ── Priority 6: Amount mismatch ───────────────────────────────────
            elif abs(result["amount_diff"]) > AMOUNT_TOLERANCE:
                result["issue"] = "amount_mismatch"

            # ── Fully matched ──────────────────────────────────────────────────
            else:
                result["issue"] = "matched"

            self._results.append(result)

    # ── Convenience ────────────────────────────────────────────────────────────

    def aggregate_totals(self) -> dict:
        """High-level financial totals for the reconciliation period."""
        df = pd.DataFrame(self._results)
        txn_total = float(df["txn_amount"].apply(float).sum())
        settled_total = float(
            df["settled_amount"].dropna().apply(float).sum()
        )
        total_discrepancy = float(
            df["amount_diff"].apply(float).sum()
        )
        matched_pct = (
            len(df[df["issue"] == "matched"]) / len(df) * 100
            if len(df) else 0
        )
        return {
            "total_transactions": len(df),
            "transaction_volume_usd": round(txn_total, 2),
            "settled_volume_usd": round(settled_total, 2),
            "net_discrepancy_usd": round(total_discrepancy, 2),
            "match_rate_pct": round(matched_pct, 1),
        }
