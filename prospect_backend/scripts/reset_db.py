"""Start over: forget everything the app recorded and set every lead back to "new".

Removes data_csv/system/ (runs, AI decisions, approvals, audit, LLM calls) and
data_csv/results/. Your leads.csv, products.csv and customers.csv are kept.
Stop the backend first, otherwise it writes its state back.

Usage:
    python scripts/reset_db.py               # wipe the recorded work
    python scripts/reset_db.py --keep-users  # keep users + sessions
"""

from __future__ import annotations

import argparse

from insurance_poc.config import get_settings
from insurance_poc.db import csv_store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-users", action="store_true")
    args = parser.parse_args()
    folder = get_settings().data_dir
    removed = csv_store.reset_state(folder, keep_users=args.keep_users)
    kept = " (kept users + sessions)" if args.keep_users else ""
    print(f"Reset {folder}: removed {len(removed)} file(s), all leads set to new{kept}.")


if __name__ == "__main__":
    main()
