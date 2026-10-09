"""Host runner (owner: C; see Q2 in docs/collab.md).

Owns `Run` state for a repair run. It wires A's RepairAgent, the scanner, B's checks
and deploy connector, and the evidence sink, and it holds the only path to deployment.

- State is durable in a local SQLite file, and every transition is checked against
  the PRD §6 state machine. ClickHouse receives events; it is not the authority.
- Each transition emits a `run.state` event with a stable ID.
- Deployment is claimed once per run before the connector is called. A claim with no
  recorded result (crash or timeout) makes the run `unresolved` and is never retried
  blindly; someone has to reconcile it with the host's actual state.
- A missing dependency (Guild session, deploy connector) is a real outcome. The run
  stops in `failed`/`unresolved` with the reason; nothing is substituted.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from adapters.clickhouse_events import stable_event_id
from contracts import (Candidate, CheckResult, CheckStatus, DeployRequest, DeployResult, DeployStatus, Event,
                       Observation, Run, RunState)

EMITTER = "host-runner"

S = RunState
TRANSITIONS: dict[RunState, set[RunState]] = {
    S.CREATED: {S.SCANNING},
    S.SCANNING: {S.PROPOSING},
    S.PROPOSING: {S.VALIDATING},
    S.VALIDATING: {S.READY_TO_DEPLOY},
    S.READY_TO_DEPLOY: {S.DEPLOYING},
    S.DEPLOYING: {S.VERIFYING},
    S.VERIFYING: {S.COMPLETED},
}
TERMINAL = {S.COMPLETED, S.FAILED, S.UNRESOLVED}
for _state in list(TRANSITIONS):
    TRANSITIONS[_state] |= {S.FAILED, S.UNRESOLVED}


class IllegalTransition(RuntimeError):
    pass


class EventSink(Protocol):
    def emit(self, event: Event) -> None: ...


class Scanner(Protocol):
    def scan(self, source_path: str, rule_ids: tuple[str, ...]) -> tuple[CheckResult, ...]: ...


class Repairer(Protocol):
    """A's RepairAgent: attempt_repair() and request_deploy()."""

    def attempt_repair(self, finding: CheckResult, guidance_ids: tuple[str, ...] = ()) -> Candidate: ...
    def request_deploy(self, built_image_digest: str) -> DeployRequest: ...


class DeployConnector(Protocol):
    """B5: deploy one validated image digest; no arbitrary host, URL, or command.

    observe() runs the external probes against an accepted attempt (candidate mode) and returns
    (passed, observations); reconcile() resolves interrupted attempts against the host. See Q13.
    """

    def deploy(self, request: DeployRequest) -> DeployResult: ...
    def observe(self, attempt_id: str) -> tuple[bool, tuple[Observation, ...]]: ...
    def reconcile(self) -> list[DeployResult]: ...


class RunStore:
    """Durable host state. One SQLite file; transitions are written in a transaction."""

    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, target_id TEXT NOT NULL, baseline_commit TEXT NOT NULL,
                baseline_image_digest TEXT NOT NULL, allowed_paths TEXT NOT NULL, rule_ids TEXT NOT NULL,
                test_suite_hash TEXT NOT NULL, started_at TEXT NOT NULL, state TEXT NOT NULL, seq INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transitions (
                run_id TEXT NOT NULL, seq INTEGER NOT NULL, from_state TEXT, to_state TEXT NOT NULL,
                at TEXT NOT NULL, reason TEXT, PRIMARY KEY (run_id, seq)
            );
            CREATE TABLE IF NOT EXISTS deploy_claims (
                run_id TEXT PRIMARY KEY, candidate_hash TEXT NOT NULL, image_digest TEXT NOT NULL,
                claimed_at TEXT NOT NULL, result TEXT
            );
            """
        )

    def create(self, run: Run) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,0)",
                (run.run_id, run.target_id, run.baseline_commit, run.baseline_image_digest,
                 json.dumps(run.allowed_paths), json.dumps(run.rule_ids), run.test_suite_hash,
                 run.started_at.isoformat(), run.state.value),
            )
            self._db.execute(
                "INSERT INTO transitions VALUES (?,?,?,?,?,?)",
                (run.run_id, 0, None, run.state.value, run.started_at.isoformat(), "created"),
            )

    def get(self, run_id: str) -> Run:
        row = self._db.execute(
            "SELECT run_id, target_id, baseline_commit, baseline_image_digest, allowed_paths, rule_ids, "
            "test_suite_hash, started_at, state FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return Run(row[0], row[1], row[2], row[3], tuple(json.loads(row[4])), tuple(json.loads(row[5])),
                   row[6], datetime.fromisoformat(row[7]), RunState(row[8]))

    def transition(self, run_id: str, to: RunState, reason: str | None) -> tuple[RunState, int, datetime]:
        at = datetime.now(timezone.utc)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            current, seq = self._db.execute("SELECT state, seq FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            current = RunState(current)
            if to not in TRANSITIONS.get(current, set()):
                raise IllegalTransition(f"{current.value} -> {to.value}")
            seq += 1
            self._db.execute("UPDATE runs SET state = ?, seq = ? WHERE run_id = ?", (to.value, seq, run_id))
            self._db.execute("INSERT INTO transitions VALUES (?,?,?,?,?,?)",
                             (run_id, seq, current.value, to.value, at.isoformat(), reason))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return current, seq, at

    def claim_deploy(self, run_id: str, candidate_hash: str, image_digest: str) -> bool:
        """True if this call made the claim; False if a claim already exists."""
        cur = self._db.execute(
            "INSERT OR IGNORE INTO deploy_claims VALUES (?,?,?,?,NULL)",
            (run_id, candidate_hash, image_digest, datetime.now(timezone.utc).isoformat()),
        )
        return cur.rowcount == 1

    def record_deploy_result(self, run_id: str, result: DeployResult) -> None:
        self._db.execute("UPDATE deploy_claims SET result = ? WHERE run_id = ?",
                         (json.dumps({"attempt_id": result.attempt_id, "status": result.status.value,
                                      "release_ref": result.release_ref, "error": result.error}), run_id))

    def open_claims(self) -> list[str]:
        return [r[0] for r in self._db.execute("SELECT run_id FROM deploy_claims WHERE result IS NULL")]


class HostRunner:
    def __init__(self, store: RunStore, sink: EventSink) -> None:
        self._store = store
        self._sink = sink

    def _event(self, run_id: str, event_type: str, key: str, outcome: str,
               candidate_hash: str | None = None, release_ref: str | None = None,
               detail: str | None = None, at: datetime | None = None) -> None:
        self._sink.emit(Event(
            event_id=stable_event_id(run_id, event_type, EMITTER, key),
            run_id=run_id, candidate_hash=candidate_hash, release_ref=release_ref,
            event_type=event_type, emitter=EMITTER, observed_at=at or datetime.now(timezone.utc),
            outcome=outcome, detail=detail,
        ))

    def _move(self, run_id: str, to: RunState, reason: str | None = None) -> None:
        previous, seq, at = self._store.transition(run_id, to, reason)
        self._event(run_id, "run.state", f"{seq}:{to.value}", to.value, at=at,
                    detail=json.dumps({"from": previous.value, "reason": reason}) if reason else json.dumps({"from": previous.value}))

    def create_run(self, target_id: str, baseline_commit: str, baseline_image_digest: str | None,
                   allowed_paths: tuple[str, ...], rule_ids: tuple[str, ...], test_suite_hash: str) -> Run:
        if not baseline_image_digest:
            raise ValueError("baseline image digest not recorded; a run needs a real baseline identity")
        run = Run(f"run_{uuid.uuid4().hex[:16]}", target_id, baseline_commit, baseline_image_digest,
                  allowed_paths, rule_ids, test_suite_hash, datetime.now(timezone.utc), RunState.CREATED)
        self._store.create(run)
        self._event(run.run_id, "run.state", "0:created", "created", at=run.started_at,
                    detail=json.dumps({"target": target_id, "baseline_commit": baseline_commit,
                                       "baseline_image": baseline_image_digest, "suite": test_suite_hash}))
        return run

    def execute(self, run_id: str, source_path: str, scanner: Scanner, repairer: Repairer,
                build_candidate: Callable[[Candidate], str], connector: DeployConnector | None,
                guidance_ids: tuple[str, ...] = ()) -> Run:
        """Drive one run as far as real dependencies allow. Returns the final stored Run."""
        run = self._store.get(run_id)
        try:
            self._move(run_id, S.SCANNING)
            findings = [r for r in scanner.scan(source_path, run.rule_ids) if r.status == CheckStatus.FAIL]
            self._event(run_id, "scan.baseline", "baseline", "finding" if findings else "no-finding",
                        detail=json.dumps({"findings": len(findings)}))
            if not findings:
                self._move(run_id, S.FAILED, "selected rule did not match the baseline")
                return self._store.get(run_id)

            self._move(run_id, S.PROPOSING)
            self._move(run_id, S.VALIDATING)
            candidate = repairer.attempt_repair(findings[0], guidance_ids)
            self._move(run_id, S.READY_TO_DEPLOY, f"candidate {candidate.candidate_id} passed required checks")

            image_digest = build_candidate(candidate)
            request = repairer.request_deploy(image_digest)
            if connector is None:
                self._move(run_id, S.UNRESOLVED, "deploy connector not configured")
                return self._store.get(run_id)
            return self._deploy(run_id, request, connector)
        except Exception as exc:
            current = self._store.get(run_id).state
            if current not in TERMINAL:
                self._move(run_id, S.FAILED, f"{type(exc).__name__}: {exc}"[:500])
            return self._store.get(run_id)

    def _deploy(self, run_id: str, request: DeployRequest, connector: DeployConnector) -> Run:
        if not self._store.claim_deploy(run_id, request.candidate_hash, request.built_image_digest):
            self._move(run_id, S.UNRESOLVED, "deploy already claimed for this run; reconcile before retrying")
            return self._store.get(run_id)
        self._move(run_id, S.DEPLOYING)
        result = connector.deploy(request)
        self._store.record_deploy_result(run_id, result)
        self._event(run_id, "deploy.result", result.attempt_id, result.status.value,
                    candidate_hash=request.candidate_hash, release_ref=result.release_ref,
                    detail=json.dumps({"image": result.image_digest, "error": result.error}))
        if result.status == DeployStatus.ACCEPTED:
            # Acceptance is not proof of serving; only the external probes can complete the run.
            self._move(run_id, S.VERIFYING, "deploy accepted; awaiting external observations")
            return self._verify(run_id, request, result, connector)
        elif result.status == DeployStatus.FAILED:
            self._move(run_id, S.FAILED, f"deploy failed: {result.error}")
        else:
            self._move(run_id, S.UNRESOLVED, "deploy outcome unknown")
        return self._store.get(run_id)

    def _verify(self, run_id: str, request: DeployRequest, result: DeployResult,
                connector: DeployConnector) -> Run:
        try:
            passed, observations = connector.observe(result.attempt_id)
        except Exception as exc:
            self._move(run_id, S.UNRESOLVED, f"external probes could not run: {type(exc).__name__}: {exc}"[:500])
            return self._store.get(run_id)
        for o in observations:
            self._event(run_id, "probe.observed", f"{result.attempt_id}:{o.probe_id}", str(o.status_code),
                        candidate_hash=request.candidate_hash, release_ref=o.release_ref, at=o.observed_at,
                        detail=json.dumps({"probe": o.probe_id, "url": o.url, "body_sha256": o.body_digest,
                                           "result": o.redacted_result})[:2000])
        if not observations:
            self._move(run_id, S.UNRESOLVED, "external probes returned no observations")
            return self._store.get(run_id)
        verdict = "external probes passed" if passed else "external probes failed"
        return self.complete(run_id, passed, f"{verdict} ({len(observations)} observations, {result.release_ref})")

    def reconcile_after_restart(self, connector: DeployConnector | None = None) -> list[str]:
        """Ask the connector what actually exists first, then mark remaining open claims unresolved.

        Never redeploys. A reconciled ACCEPTED/FAILED result is recorded as a deploy.result event;
        the run itself still needs an operator decision, so it is marked unresolved with that outcome.
        """
        if connector is not None:
            for r in connector.reconcile():
                self._sink.emit(Event(
                    event_id=stable_event_id("reconcile", "deploy.result", EMITTER, f"{r.attempt_id}:{r.status.value}"),
                    run_id="reconcile", candidate_hash=None, release_ref=r.release_ref, event_type="deploy.result",
                    emitter=EMITTER, observed_at=datetime.now(timezone.utc), outcome=r.status.value,
                    detail=json.dumps({"attempt": r.attempt_id, "image": r.image_digest, "error": r.error})))
        marked = []
        for run_id in self._store.open_claims():
            if self._store.get(run_id).state not in TERMINAL:
                self._move(run_id, S.UNRESOLVED, "restart found a deploy claim without a result")
                marked.append(run_id)
        return marked

    def complete(self, run_id: str, observations_passed: bool, reason: str) -> Run:
        """Called with B5's external probe verdict for a run in `verifying`."""
        self._move(run_id, S.COMPLETED if observations_passed else S.FAILED, reason)
        return self._store.get(run_id)


__all__ = ["HostRunner", "IllegalTransition", "RunStore", "TRANSITIONS"]
