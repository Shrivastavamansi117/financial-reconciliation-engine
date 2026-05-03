"""
data_generator.py
-----------------
Generates synthetic transaction and settlement datasets with controlled
injection of reconciliation edge cases.

Assumptions:
  - Base currency: USD
  - Settlement window: T+1 or T+2 business days (normal)
  - Rounding: settlements truncate sub-cent values instead of rounding
  - ~5% of transactions fall into each edge-case category
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import List, Tuple

import pandas as pd


# ─── Config ────────────────────────────────────────────────────────────────────

SEED = 42
BASE_TXN_COUNT = 200
EDGE_CASE_COUNTS = {
    "timing_mismatch": 8,   # settled in next calendar month
    "rounding_diff": 10,    # tiny per-record diff that compounds
    "duplicate": 6,         # same txn_id appears twice in settlements
    "orphan_refund": 5,     # refund with no matching original
    "missing_settlement": 7, # transaction never settled
}

MERCHANTS = ["Acme Corp", "ByteShop", "CloudSoft", "DataMart", "EdgePay"]
random.seed(SEED)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _business_days_later(start: date, n: int) -> date:
    """Advance `n` business days from `start`."""
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon–Fri
            added += 1
    return d


def _random_amount() -> Decimal:
    """Generate a realistic transaction amount between $1 and $9,999."""
    return Decimal(str(round(random.uniform(1.0, 9999.0), 2)))


def _next_month_date(d: date) -> date:
    """Return a date 32–45 days later (guarantees next calendar month)."""
    return d + timedelta(days=random.randint(32, 45))


# ─── Core generator ────────────────────────────────────────────────────────────

def generate_datasets(
    base_count: int = BASE_TXN_COUNT,
    start_date: date = date(2024, 1, 2),
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
        transactions_df  – payment-platform records
        settlements_df   – bank settlement records
    """
    transactions: List[dict] = []
    settlements: List[dict] = []

    txn_id_counter = 1000

    # ── 1. Normal transactions ─────────────────────────────────────────────────
    for i in range(base_count):
        txn_date = start_date + timedelta(days=random.randint(0, 27))
        amount = _random_amount()
        txn_id = f"TXN{txn_id_counter:05d}"
        txn_id_counter += 1

        transactions.append({
            "txn_id": txn_id,
            "merchant": random.choice(MERCHANTS),
            "txn_date": txn_date,
            "amount": amount,
            "status": "captured",
            "edge_case": None,
        })

        # Normal settlement: T+1 or T+2
        settle_days = random.choice([1, 2])
        settlements.append({
            "settlement_id": f"SET{txn_id_counter:05d}",
            "txn_id": txn_id,
            "settlement_date": _business_days_later(txn_date, settle_days),
            "settled_amount": amount,
            "edge_case": None,
        })

    # ── 2. Edge Case: Timing mismatch (next-month settlement) ──────────────────
    for _ in range(EDGE_CASE_COUNTS["timing_mismatch"]):
        txn_date = start_date + timedelta(days=random.randint(20, 27))
        amount = _random_amount()
        txn_id = f"TXN{txn_id_counter:05d}"
        txn_id_counter += 1

        transactions.append({
            "txn_id": txn_id,
            "merchant": random.choice(MERCHANTS),
            "txn_date": txn_date,
            "amount": amount,
            "status": "captured",
            "edge_case": "timing_mismatch",
        })
        settlements.append({
            "settlement_id": f"SET{txn_id_counter:05d}",
            "txn_id": txn_id,
            "settlement_date": _next_month_date(txn_date),
            "settled_amount": amount,
            "edge_case": "timing_mismatch",
        })

    # ── 3. Edge Case: Rounding differences ────────────────────────────────────
    for _ in range(EDGE_CASE_COUNTS["rounding_diff"]):
        txn_date = start_date + timedelta(days=random.randint(0, 27))
        amount = _random_amount()
        txn_id = f"TXN{txn_id_counter:05d}"
        txn_id_counter += 1

        # Settlement truncates instead of rounding → off by $0.01
        settled = amount.quantize(Decimal("0.01"), rounding=ROUND_DOWN) - Decimal("0.01")

        transactions.append({
            "txn_id": txn_id,
            "merchant": random.choice(MERCHANTS),
            "txn_date": txn_date,
            "amount": amount,
            "status": "captured",
            "edge_case": "rounding_diff",
        })
        settlements.append({
            "settlement_id": f"SET{txn_id_counter:05d}",
            "txn_id": txn_id,
            "settlement_date": _business_days_later(txn_date, 1),
            "settled_amount": max(Decimal("0.01"), settled),
            "edge_case": "rounding_diff",
        })

    # ── 4. Edge Case: Duplicate settlements ───────────────────────────────────
    for _ in range(EDGE_CASE_COUNTS["duplicate"]):
        txn_date = start_date + timedelta(days=random.randint(0, 27))
        amount = _random_amount()
        txn_id = f"TXN{txn_id_counter:05d}"
        txn_id_counter += 1

        transactions.append({
            "txn_id": txn_id,
            "merchant": random.choice(MERCHANTS),
            "txn_date": txn_date,
            "amount": amount,
            "status": "captured",
            "edge_case": "duplicate",
        })
        # Two identical settlement records
        for j in range(2):
            settlements.append({
                "settlement_id": f"SET{txn_id_counter:05d}-{j}",
                "txn_id": txn_id,
                "settlement_date": _business_days_later(txn_date, 1),
                "settled_amount": amount,
                "edge_case": "duplicate",
            })

    # ── 5. Edge Case: Orphan refunds (no matching original) ───────────────────
    for _ in range(EDGE_CASE_COUNTS["orphan_refund"]):
        txn_date = start_date + timedelta(days=random.randint(0, 27))
        amount = _random_amount()
        txn_id = f"TXN{txn_id_counter:05d}"
        txn_id_counter += 1

        # Refund only in transactions — no corresponding original or settlement
        transactions.append({
            "txn_id": txn_id,
            "merchant": random.choice(MERCHANTS),
            "txn_date": txn_date,
            "amount": -amount,   # negative = refund
            "status": "refunded",
            "edge_case": "orphan_refund",
        })
        # No settlement entry added

    # ── 6. Edge Case: Missing settlements ─────────────────────────────────────
    for _ in range(EDGE_CASE_COUNTS["missing_settlement"]):
        txn_date = start_date + timedelta(days=random.randint(0, 27))
        amount = _random_amount()
        txn_id = f"TXN{txn_id_counter:05d}"
        txn_id_counter += 1

        transactions.append({
            "txn_id": txn_id,
            "merchant": random.choice(MERCHANTS),
            "txn_date": txn_date,
            "amount": amount,
            "status": "captured",
            "edge_case": "missing_settlement",
        })
        # No settlement entry added

    # ── Build DataFrames ───────────────────────────────────────────────────────
    txn_df = pd.DataFrame(transactions)
    txn_df["amount"] = txn_df["amount"].apply(Decimal)

    set_df = pd.DataFrame(settlements)
    set_df["settled_amount"] = set_df["settled_amount"].apply(Decimal)

    # Shuffle so edge cases aren't obviously grouped
    txn_df = txn_df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    set_df = set_df.sample(frac=1, random_state=SEED).reset_index(drop=True)

    return txn_df, set_df
