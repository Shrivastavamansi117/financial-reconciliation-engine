"""
reporter.py
-----------
Generates console and CSV reconciliation reports from Reconciler output.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _ensure_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def print_report(reconciler) -> None:
    """Pretty-print a reconciliation report to stdout."""
    totals = reconciler.aggregate_totals()
    summary = reconciler.summary()

    width = 70
    print("\n" + "═" * width)
    print("  FINANCIAL RECONCILIATION REPORT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * width)

    print("\n📊  AGGREGATE TOTALS")
    print(f"  Total transactions       : {totals['total_transactions']:>8,}")
    print(f"  Transaction volume (USD) : {totals['transaction_volume_usd']:>12,.2f}")
    print(f"  Settled volume (USD)     : {totals['settled_volume_usd']:>12,.2f}")
    print(f"  Net discrepancy (USD)    : {totals['net_discrepancy_usd']:>12,.2f}")
    print(f"  Match rate               : {totals['match_rate_pct']:>8.1f}%")

    print("\n📋  ISSUE BREAKDOWN")
    print(f"  {'Issue':<35} {'Count':>6} {'Txn Amount':>14} {'Impact':>12}")
    print("  " + "-" * 68)

    for _, row in summary.iterrows():
        label = row["issue_label"]
        count = row["count"]
        txn_amt = row["total_txn_amount"]
        impact = row["total_impact"]
        impact_str = f"${impact:,.2f}" if impact != 0 else "—"
        print(f"  {label:<35} {count:>6,}   ${txn_amt:>12,.2f}   {impact_str:>11}")

    print("\n" + "═" * width + "\n")


def save_reports(reconciler) -> dict[str, Path]:
    """Save summary and detail CSVs; return file paths."""
    _ensure_output_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary_path = OUTPUT_DIR / f"reconciliation_summary_{ts}.csv"
    detail_path = OUTPUT_DIR / f"reconciliation_detail_{ts}.csv"

    reconciler.summary().to_csv(summary_path, index=False)
    reconciler.details().to_csv(detail_path, index=False)

    print(f"  ✔ Summary saved → {summary_path}")
    print(f"  ✔ Details saved → {detail_path}")

    return {"summary": summary_path, "detail": detail_path}
