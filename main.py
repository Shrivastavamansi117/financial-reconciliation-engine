"""
main.py
-------
CLI entry point — generates data, runs reconciliation, prints report, saves CSVs.

Usage:  python main.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from data_generator import generate_datasets
from reconciler import Reconciler
from reporter import print_report, save_reports


def main():
    print("\n🔄 Generating synthetic datasets…")
    transactions, settlements = generate_datasets()
    print(f"   ✔ {len(transactions)} transactions | {len(settlements)} settlement records")

    print("⚙️  Running reconciliation engine…")
    recon = Reconciler(transactions, settlements)
    recon.run()
    print("   ✔ Complete")

    print_report(recon)
    save_reports(recon)

    print("\n💡 To launch the interactive dashboard:")
    print("   streamlit run app.py\n")


if __name__ == "__main__":
    main()
