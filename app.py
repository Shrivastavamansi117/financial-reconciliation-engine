"""
app.py  –  Streamlit Reconciliation Dashboard
----------------------------------------------
Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import streamlit as st

from data_generator import generate_datasets
from reconciler import Reconciler, ISSUE_LABELS

# ─── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="FinRecon Dashboard",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Styles ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}
.metric-card {
    background: #0f1117;
    border: 1px solid #2a2d3a;
    border-radius: 8px;
    padding: 20px;
    text-align: center;
}
.metric-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2rem;
    font-weight: 600;
    color: #00d4aa;
}
.metric-label {
    font-size: 0.8rem;
    color: #8b8fa8;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}
.issue-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
}
.stDataFrame { font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚖️ FinRecon")
    st.markdown("*Financial Reconciliation Engine*")
    st.divider()

    base_count = st.slider("Base transaction count", 50, 500, 200, step=50)
    seed = st.number_input("Random seed", value=42, step=1)

    run_btn = st.button("🔄 Run Reconciliation", use_container_width=True, type="primary")

    st.divider()
    st.markdown("**Edge case injection:**")
    st.markdown("- 📅 Timing mismatch: 8")
    st.markdown("- 💲 Rounding diff: 10")
    st.markdown("- 🔁 Duplicate: 6")
    st.markdown("- ↩️ Orphan refund: 5")
    st.markdown("- ❌ Missing settlement: 7")

# ─── Session state ─────────────────────────────────────────────────────────────

if "recon" not in st.session_state or run_btn:
    with st.spinner("Generating data & running reconciliation…"):
        import data_generator as dg
        dg.SEED = int(seed)
        import random
        random.seed(int(seed))
        txns, sets = generate_datasets(base_count=base_count)
        recon = Reconciler(txns, sets).run()
        st.session_state["recon"] = recon
        st.session_state["txns"] = txns
        st.session_state["sets"] = sets

recon: Reconciler = st.session_state["recon"]
totals = recon.aggregate_totals()
summary = recon.summary()
details = recon.details()

# ─── Header ────────────────────────────────────────────────────────────────────

st.markdown("# ⚖️ Financial Reconciliation Dashboard")
st.markdown(f"*Reconciling {totals['total_transactions']} transactions · January 2024*")
st.divider()

# ─── KPI row ───────────────────────────────────────────────────────────────────

c1, c2, c3, c4, c5 = st.columns(5)

def kpi(col, label, value, prefix="", suffix="", color="#00d4aa"):
    col.markdown(f"""
    <div class="metric-card">
        <div class="metric-value" style="color:{color}">{prefix}{value}{suffix}</div>
        <div class="metric-label">{label}</div>
    </div>
    """, unsafe_allow_html=True)

kpi(c1, "Total Transactions", f"{totals['total_transactions']:,}")
kpi(c2, "Transaction Volume", f"{totals['transaction_volume_usd']:,.0f}", prefix="$")
kpi(c3, "Settled Volume", f"{totals['settled_volume_usd']:,.0f}", prefix="$")

disc = totals['net_discrepancy_usd']
disc_color = "#ff4b6e" if abs(disc) > 0 else "#00d4aa"
kpi(c4, "Net Discrepancy", f"{disc:,.2f}", prefix="$", color=disc_color)

match_pct = totals['match_rate_pct']
match_color = "#00d4aa" if match_pct >= 90 else "#f5a623" if match_pct >= 75 else "#ff4b6e"
kpi(c5, "Match Rate", f"{match_pct:.1f}", suffix="%", color=match_color)

st.markdown("<br>", unsafe_allow_html=True)

# ─── Summary table + bar chart ─────────────────────────────────────────────────

col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.markdown("### 📋 Issue Breakdown")

    display_summary = summary[summary["issue"] != "matched"].copy()
    display_summary = display_summary.rename(columns={
        "issue_label": "Issue",
        "count": "Count",
        "total_txn_amount": "Txn Amount ($)",
        "total_impact": "Financial Impact ($)",
    })[["Issue", "Count", "Txn Amount ($)", "Financial Impact ($)"]]

    # Color the impact column
    def color_impact(val):
        if val < 0:
            return "color: #ff4b6e"
        elif val > 0:
            return "color: #f5a623"
        return ""

    styled = display_summary.style.applymap(color_impact, subset=["Financial Impact ($)"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Also show matched count
    matched_row = summary[summary["issue"] == "matched"]
    if not matched_row.empty:
        mc = matched_row["count"].iloc[0]
        st.success(f"✅ {mc} transactions fully reconciled ({mc/totals['total_transactions']*100:.1f}%)")

with col_right:
    st.markdown("### 📊 Issue Distribution")
    chart_data = summary[summary["issue"] != "matched"][["issue_label", "count"]].set_index("issue_label")
    st.bar_chart(chart_data, color="#00d4aa")

st.divider()

# ─── Filters + detail table ────────────────────────────────────────────────────

st.markdown("### 🔍 Row-Level Detail")

col_f1, col_f2 = st.columns([2, 3])

with col_f1:
    issue_options = ["All issues"] + list(ISSUE_LABELS.values())
    selected_issue = st.selectbox("Filter by issue", issue_options)

with col_f2:
    merchant_options = ["All merchants"] + sorted(details["merchant"].unique().tolist())
    selected_merchant = st.selectbox("Filter by merchant", merchant_options)

filtered = details.copy()
if selected_issue != "All issues":
    issue_key = {v: k for k, v in ISSUE_LABELS.items()}[selected_issue]
    filtered = filtered[filtered["issue"] == issue_key]

if selected_merchant != "All merchants":
    filtered = filtered[filtered["merchant"] == selected_merchant]

# Format display columns
display_cols = [
    "txn_id", "merchant", "txn_date", "txn_amount",
    "settlement_date", "settled_amount", "amount_diff",
    "business_days_to_settle", "issue_label"
]
display_df = filtered[display_cols].rename(columns={
    "txn_id": "Txn ID",
    "merchant": "Merchant",
    "txn_date": "Txn Date",
    "txn_amount": "Txn Amount",
    "settlement_date": "Settle Date",
    "settled_amount": "Settled Amt",
    "amount_diff": "Diff",
    "business_days_to_settle": "Biz Days",
    "issue_label": "Issue",
})

def highlight_issues(row):
    issue = row["Issue"]
    if "Missing" in issue or "Orphan" in issue:
        return ["background-color: #2a0a14"] * len(row)
    elif "Mismatch" in issue or "Amount" in issue:
        return ["background-color: #2a1f0a"] * len(row)
    elif "Duplicate" in issue:
        return ["background-color: #0a1a2a"] * len(row)
    elif "Delayed" in issue or "Timing" in issue:
        return ["background-color: #1a1a0a"] * len(row)
    return [""] * len(row)

st.markdown(f"*Showing {len(display_df):,} of {len(details):,} records*")
st.dataframe(
    display_df.style.apply(highlight_issues, axis=1),
    use_container_width=True,
    hide_index=True,
    height=400,
)

# ─── Download ──────────────────────────────────────────────────────────────────

st.divider()
st.markdown("### 💾 Export")

col_d1, col_d2, _ = st.columns([1, 1, 2])

with col_d1:
    summary_csv = summary.to_csv(index=False).encode()
    st.download_button(
        "⬇️ Download Summary CSV",
        data=summary_csv,
        file_name="recon_summary.csv",
        mime="text/csv",
        use_container_width=True,
    )

with col_d2:
    detail_csv = details.to_csv(index=False).encode()
    st.download_button(
        "⬇️ Download Detail CSV",
        data=detail_csv,
        file_name="recon_detail.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ─── Assumptions footer ────────────────────────────────────────────────────────

with st.expander("📌 Assumptions & Methodology"):
    st.markdown("""
    **Matching Logic**
    - Primary match key: `txn_id` (exact string match)
    - No fuzzy fallback implemented (extension point if needed)

    **Classification Priority** *(applied in order, first match wins)*
    1. **Duplicate** — `txn_id` appears >1 time in settlements
    2. **Orphan Refund** — negative amount with no settlement record
    3. **Missing Settlement** — no settlement record found
    4. **Timing Mismatch** — settlement month ≠ transaction month
    5. **Delayed Settlement** — >2 business days (Mon–Fri, excl. weekends)
    6. **Amount Mismatch** — settled amount ≠ transaction amount (strict $0.00 tolerance)
    7. **Matched** — all checks pass ✓

    **Financial Impact Definition**
    - Missing settlement: `-txn_amount` (revenue not received)
    - Orphan refund: `refund_amount` (liability with no offsetting original)
    - Amount mismatch: `settled_amount - txn_amount` (positive = overpaid, negative = underpaid)
    - Duplicates: `settled_amount` of duplicate row (potential double-debit)

    **Edge Case Injection Counts**
    | Scenario | Injected |
    |---|---|
    | Timing mismatch (next month) | 8 |
    | Rounding difference ($0.01) | 10 |
    | Duplicate settlements | 6 |
    | Orphan refunds | 5 |
    | Missing settlements | 7 |
    """)
