import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from contracts import Candidate, CheckResult, CheckStatus, DeployRequest, DeployResult, DeployStatus, RunState
from server.runner import HostRunner, IllegalTransition, RunStore

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


class ListSink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def finding(status=CheckStatus.FAIL):
    return CheckResult("rule", "", status, NOW, None, "semgrep")


class Scanner:
    def __init__(self, status=CheckStatus.FAIL):
        self.status = status

    def scan(self, source_path, rule_ids):
        return (finding(self.status),)


class Repairer:
    """Stands in for RepairAgent in tests; production uses agent.RepairAgent."""

    def __init__(self, error=None):
        self.error = error

    def attempt_repair(self, finding, guidance_ids=()):
        if self.error:
            raise self.error
        return Candidate("c1", "r", "base", "+++ b/routes/search.ts\n", "h1", "test-double")

    def request_deploy(self, digest):
        return DeployRequest("r", "h1", digest)


class Connector:
    def __init__(self, status):
        self.status = status
        self.calls = 0

    def deploy(self, request):
        self.calls += 1
        return DeployResult("a1", "juice-shop", request.built_image_digest, "rel-1", self.status)


@pytest.fixture
def runner(tmp_path):
    sink = ListSink()
    store = RunStore(tmp_path / "host.db")
    return HostRunner(store, sink), store, sink


def new_run(r):
    return r.create_run("juice-shop", "5658473c", "sha256:base", ("routes/search.ts",), ("rule",), "suite")


def states(sink, run_id):
    return [e.outcome for e in sink.events if e.event_type == "run.state" and e.run_id == run_id]


def test_run_requires_recorded_baseline_digest(runner):
    r, _, _ = runner
    with pytest.raises(ValueError):
        r.create_run("juice-shop", "5658473c", None, ("routes/search.ts",), ("rule",), "suite")


def test_accepted_deploy_reaches_verifying_not_completed(runner):
    r, store, sink = runner
    run = new_run(r)
    final = r.execute(run.run_id, "/src", Scanner(), Repairer(), lambda c: "sha256:cand", Connector(DeployStatus.ACCEPTED))
    assert final.state == RunState.VERIFYING
    assert states(sink, run.run_id) == [
        "created", "scanning", "proposing", "validating", "ready_to_deploy", "deploying", "verifying"]
    assert r.complete(run.run_id, True, "external probes passed").state == RunState.COMPLETED


def test_missing_connector_is_unresolved_not_success(runner):
    r, _, _ = runner
    run = new_run(r)
    assert r.execute(run.run_id, "/src", Scanner(), Repairer(), lambda c: "d", None).state == RunState.UNRESOLVED


def test_agent_failure_is_recorded_as_failed_with_reason(runner):
    r, _, sink = runner
    run = new_run(r)
    final = r.execute(run.run_id, "/src", Scanner(), Repairer(RuntimeError("no Guild session")), lambda c: "d", None)
    assert final.state == RunState.FAILED
    assert "no Guild session" in sink.events[-1].detail


def test_no_baseline_finding_fails_run(runner):
    r, _, _ = runner
    run = new_run(r)
    assert r.execute(run.run_id, "/src", Scanner(CheckStatus.PASS), Repairer(), lambda c: "d", None).state == RunState.FAILED


def test_deploy_claim_is_once_and_restart_marks_unresolved(runner, tmp_path):
    r, store, sink = runner
    run = new_run(r)
    store.claim_deploy(run.run_id, "h1", "sha256:cand")  # simulate a claim left by a crashed process
    connector = Connector(DeployStatus.ACCEPTED)
    final = r.execute(run.run_id, "/src", Scanner(), Repairer(), lambda c: "sha256:cand", connector)
    assert final.state == RunState.UNRESOLVED and connector.calls == 0

    run2 = new_run(r)
    for s in (RunState.SCANNING, RunState.PROPOSING, RunState.VALIDATING, RunState.READY_TO_DEPLOY, RunState.DEPLOYING):
        store.transition(run2.run_id, s, None)
    store.claim_deploy(run2.run_id, "h2", "sha256:x")
    restarted = HostRunner(RunStore(tmp_path / "host.db"), sink)
    assert restarted.reconcile_after_restart() == [run2.run_id]
    assert store.get(run2.run_id).state == RunState.UNRESOLVED


def test_illegal_transition_rejected_and_state_unchanged(runner):
    r, store, _ = runner
    run = new_run(r)
    with pytest.raises(IllegalTransition):
        store.transition(run.run_id, RunState.DEPLOYING, None)
    assert store.get(run.run_id).state == RunState.CREATED


def test_state_event_ids_are_stable_per_transition(runner):
    r, _, sink = runner
    run = new_run(r)
    r.execute(run.run_id, "/src", Scanner(), Repairer(), lambda c: "d", None)
    ids = [e.event_id for e in sink.events if e.event_type == "run.state"]
    assert len(ids) == len(set(ids))
