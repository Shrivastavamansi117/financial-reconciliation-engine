# ⚡ FinRecon Pro — Financial Reconciliation System

A production-grade Streamlit dashboard for reconciling internal transaction ledgers with bank settlements, detecting discrepancies, and generating actionable insights.

---

# 🧠 Problem Statement

A payments platform records transactions instantly when a customer pays, while the bank settles funds after 1–2 days.
At month end, both records should match — but in reality, they often don’t.

This project builds a reconciliation system to:

* Compare platform transactions with bank settlements
* Identify mismatches
* Explain the root cause of discrepancies

---

# 🎯 Objective

Detect and classify the following gap types:

* **Delayed Settlement** — Transactions settled in the next month
* **Rounding Differences** — Small discrepancies visible only at aggregate level
* **Duplicate Records** — Same transaction appearing multiple times
* **Missing Settlement** — Transaction exists but no bank record
* **Orphan Settlement / Refund** — Settlement exists without original transaction

---

# 🧠 Assumptions

* `txn_id` uniquely identifies transactions
* Settlement delay is within 1–2 days
* Refunds are represented as negative amounts
* Matching is primarily based on `txn_id`, with fallback logic if needed

---

# 🚀 Features

* **Synthetic data generator** with configurable edge cases
* **Reconciliation engine** with configurable match tolerance
* **6 issue types detected**:

  * Amount mismatch
  * Missing settlement
  * Duplicate settlement
  * Orphan settlement
  * Timing mismatch (delayed settlement)
  * Rounding discrepancy (aggregate-level)
* **Interactive dashboard**:

  * Total transactions, volume, discrepancy, match rate
  * Issue breakdown and distribution charts
  * Row-level debugging table
* **CSV upload support** for real data reconciliation
* **CSV export** for reports

---

# ⚙️ Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

# 📂 CSV Upload Format

## Transactions CSV

| Column   | Type   | Example    |
| -------- | ------ | ---------- |
| txn_id   | string | TXN_ABC123 |
| date     | date   | 2024-03-15 |
| merchant | string | Stripe     |
| category | string | SALE       |
| currency | string | USD        |
| amount   | float  | 1250.00    |
| status   | string | COMPLETED  |

---

## Bank Settlements CSV

| Column          | Type   | Example    |
| --------------- | ------ | ---------- |
| settlement_id   | string | STL_ABC123 |
| txn_ref         | string | TXN_ABC123 |
| settlement_date | date   | 2024-03-16 |
| merchant        | string | Stripe     |
| settled_amount  | float  | 1250.00    |

---

# 🧪 Test Coverage

The system has been validated against the following scenarios:

1. Perfect match → No discrepancies
2. Missing settlement → Correctly flagged
3. Duplicate record → Detected
4. Delayed settlement → Classified as timing mismatch
5. Rounding difference → Detected in aggregate totals
6. Orphan settlement/refund → Flagged correctly

---

# 📊 Output

The system generates:

* Summary metrics (transactions, volume, discrepancy, match rate)
* Issue classification report (count + financial impact)
* Visual distribution of discrepancies
* Row-level traceability for debugging

---

# ⚠️ Limitations

* Assumes consistent transaction identifiers across systems
* Does not handle partial or split settlements
* Synthetic data may not fully represent real-world complexity

---

# 💡 Future Improvements

* Support for partial settlements and split payments
* ML-based anomaly detection
* Real-time reconciliation pipeline
* Integration with banking APIs

---
