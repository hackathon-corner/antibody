import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from contracts import (Candidate, CheckResult, CheckStatus, DeployRequest, DeployResult, DeployStatus, Observation,
                       RunState)
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


def observation(probe_id="search.ordinary"):
    return Observation("http://lease.example.invalid", "juice-shop", probe_id, "akash:1", 200, "d" * 64, NOW, "pass")


class Connector:
    def __init__(self, status, passed=True, observations=None, observe_error=None):
        self.status = status
        self.calls = 0
        self.passed = passed
        self.observations = (observation(), observation("security.injection")) if observations is None else observations
        self.observe_error = observe_error

    def deploy(self, request):
        self.calls += 1
        return DeployResult("a1", "juice-shop", request.built_image_digest, "akash:1", self.status)

    def observe(self, attempt_id):
        if self.observe_error:
            raise self.observe_error
        return self.passed, self.observations

    def reconcile(self):
        return []


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


def test_accepted_deploy_completes_only_after_external_probes_pass(runner):
    r, store, sink = runner
    run = new_run(r)
    final = r.execute(run.run_id, "/src", Scanner(), Repairer(), lambda c: "sha256:cand", Connector(DeployStatus.ACCEPTED))
    assert final.state == RunState.COMPLETED
    assert states(sink, run.run_id) == [
        "created", "scanning", "proposing", "validating", "ready_to_deploy", "deploying", "verifying", "completed"]
    probes = [e for e in sink.events if e.event_type == "probe.observed"]
    assert [e.release_ref for e in probes] == ["akash:1", "akash:1"] and all(e.candidate_hash == "h1" for e in probes)


@pytest.mark.parametrize("connector, expected", [
    (Connector(DeployStatus.ACCEPTED, passed=False), RunState.FAILED),
    (Connector(DeployStatus.ACCEPTED, observe_error=TimeoutError("lease not ready")), RunState.UNRESOLVED),
    (Connector(DeployStatus.ACCEPTED, observations=()), RunState.UNRESOLVED),
])
def test_probe_failures_never_complete(runner, connector, expected):
    r, _, _ = runner
    run = new_run(r)
    assert r.execute(run.run_id, "/src", Scanner(), Repairer(), lambda c: "d", connector).state == expected


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
