"""C2 completion check: record the real build-target spike run as events, then query them back.

Usage: .venv/bin/python scripts/clickhouse_record_spike.py <github-actions-run-id>

Event times and outcomes are read from the GitHub Actions API (via `gh`), not typed in.
Re-running is safe: event IDs are stable, and reads deduplicate by event_id.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adapters.clickhouse_events import ClickHouseEventStore, stable_event_id
from contracts import Event

REPO = "hackathon-corner/antibody"
STEPS = {
    "Build and push": "target.build",
    "Independent checks": "checks.baseline",
    "Pinned Semgrep scan": "scan.semgrep",
}


def main(run_id: str) -> None:
    jobs = json.loads(subprocess.run(
        ["gh", "api", f"repos/{REPO}/actions/runs/{run_id}/jobs"],
        check=True, capture_output=True, text=True,
    ).stdout)
    steps = {s["name"]: s for job in jobs["jobs"] for s in job["steps"]}
    artifact_ref = f"https://github.com/{REPO}/actions/runs/{run_id}"
    evidence_run_id = f"spike-gha-{run_id}"
    emitter = "github-actions:build-target"

    events = []
    for step_name, event_type in STEPS.items():
        step = steps.get(step_name)
        if step is None or step.get("completed_at") is None:
            print(f"skip {step_name}: not present or not completed")
            continue
        events.append(Event(
            event_id=stable_event_id(evidence_run_id, event_type, emitter, f"{run_id}:{step['number']}"),
            run_id=evidence_run_id,
            candidate_hash=None,
            release_ref=None,
            event_type=event_type,
            emitter=emitter,
            observed_at=datetime.fromisoformat(step["completed_at"].replace("Z", "+00:00")),
            outcome=step["conclusion"] or "unknown",
            artifact_ref=artifact_ref,
        ))

    store = ClickHouseEventStore.from_env()
    store.ensure_schema()
    print(f"inserted {store.insert(events)} events")
    for e in store.events_for_run(evidence_run_id):
        print(f"{e.observed_at.isoformat()}  {e.event_type:<16} {e.outcome:<8} {e.event_id}")


if __name__ == "__main__":
    main(sys.argv[1])
