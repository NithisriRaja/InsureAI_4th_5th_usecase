"""Acquisition demo against a running API.

python scripts/run_acquisition_demo.py            # run 4 showcase seed leads
python scripts/run_acquisition_demo.py --all      # every seeded lead
python scripts/run_acquisition_demo.py --approve  # also approve the first sales item
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _demo_client import client, login, show, wait_runs  # noqa: E402

SHOWCASE = ["lead_l01", "lead_l07", "lead_l08", "lead_l09"]  # hot, injection, protected, refer


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true")
    p.add_argument("--approve", action="store_true")
    args = p.parse_args()
    c = client()

    if args.all:
        lead_ids = [x["id"] for x in c.get("/leads", params={"limit": 200}).json()["items"]]
    else:
        lead_ids = SHOWCASE
    print(f"\nTriggering {len(lead_ids)} acquisition runs...")
    run_ids = [c.post(f"/leads/{lid}/runs").json()["id"] for lid in lead_ids]
    runs = wait_runs(c, run_ids)

    for run in runs:
        if run.get("recommendation_id"):
            show(c.get(f"/recommendations/{run['recommendation_id']}").json())

    if args.approve:
        h = login(c, "Demo Sales", "sales")
        queue = c.get(
            "/recommendations", params={"queue": "sales", "status": "pending_approval"}
        ).json()["items"]
        if queue:
            rec = queue[0]
            r = c.post(
                f"/approvals/{rec['id']}/approve",
                headers=h,
                json={"expected_version": rec["version"]},
            )
            print(f"\nApproved {rec['id']}: {r.status_code} {r.json()}")
            r = c.post(
                f"/approvals/{rec['id']}/approve",
                headers=h,
                json={"expected_version": rec["version"]},
            )
            print(f"Second approval (expected 409): {r.status_code} {r.json()['error']['code']}")
    print("\nStats:", c.get("/stats").json()["llm"])


if __name__ == "__main__":
    main()
