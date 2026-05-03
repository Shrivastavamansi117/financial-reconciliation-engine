# Financial Reconciliation Engine

This project reconciles transactions recorded by a payment platform with bank settlements.

## Features

* Synthetic data generation
* Detection of mismatches:

  * Missing settlements
  * Delayed settlements
  * Duplicate transactions
  * Rounding discrepancies
  * Orphan refunds
* Streamlit dashboard for visualization

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```
