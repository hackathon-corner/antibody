"""A6 adversarial test: an intentionally overbroad/bad candidate submitted
through the same validation path as a real one must be rejected, and the
host must never request deployment for it (PRD section 4 and section 10
item 4: origin is disclosed, not attributed to the model unless the model
actually produced it).

Two failure modes, both must be caught before deploy:
1. Scope violation -- touches a forbidden path. Caught by CandidateValidator
   before B's checks ever run.
2. "Closed the hole by closing the business" -- stays in scope but disables
   search. CandidateValidator can't see this (it's not a scope violation);
   B's independent behavior checks must catch it.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent import CandidateValidator, MaxAttemptsExceeded, RepairAgent
from contracts import Candidate, CheckResult, CheckStatus

ALLOWED_PATH = "routes/search.ts"
BASE_COMMIT = "abc123"
SOURCE = {ALLOWED_PATH: "original vulnerable content"}


def make_finding() -> CheckResult:
    return CheckResult(
        check_id="sqli-01",
        candidate_hash="",
        status=CheckStatus.FAIL,
        observed_at=datetime.now(timezone.utc),
        artifact_ref=None,
        adapter_origin="semgrep",
        detail="1 match(es) at routes/search.ts:23",
    )


def diff(path: str, old: str = "old", new: str = "new") -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n"


class SupplierAdapter:
    """Stands in for an operator-supplied bad candidate, not model output --
    origin is disclosed accurately, never claimed as the agent's own work."""

    def __init__(self, patch: str) -> None:
        self._patch = patch

    def propose(self, run_id, base_commit, finding, source_files, guidance_ids=(), attempt_number=1) -> Candidate:
        return Candidate(
            candidate_id=f"bad-{attempt_number}",
            run_id=run_id,
            base_commit=base_commit,
            patch=self._patch,
            content_hash="",
            origin="operator-supplied-bad-candidate",
            attempt_number=attempt_number,
        )


def test_scope_violating_candidate_never_reaches_checks_or_deploy() -> None:
    checks_were_called = False

    def run_checks(candidate: Candidate) -> tuple[CheckResult, ...]:
        nonlocal checks_were_called
        checks_were_called = True
        return (
            CheckResult(
                check_id="sqli-01",
                candidate_hash="",
                status=CheckStatus.PASS,
                observed_at=datetime.now(timezone.utc),
                artifact_ref=None,
                adapter_origin="behavior-suite",
            ),
        )

    bad_patch = diff(ALLOWED_PATH) + diff("tests/e2e/search.test.ts")
    validator = CandidateValidator(allowed_paths=(ALLOWED_PATH,), expected_base_commit=BASE_COMMIT)
    agent = RepairAgent(
        run_id="r1",
        base_commit=BASE_COMMIT,
        patch_adapter=SupplierAdapter(bad_patch),
        validator=validator,
        run_checks=run_checks,
        source_files=SOURCE,
    )

    with pytest.raises(MaxAttemptsExceeded):
        agent.attempt_repair(make_finding())

    assert not checks_were_called, "scope-violating candidate must be rejected before checks run"
    with pytest.raises(RuntimeError, match="no passing candidate"):
        agent.request_deploy("sha256:deadbeef")


def test_search_disabling_candidate_passes_scope_but_fails_checks_and_blocks_deploy() -> None:
    """The 'closed the hole by closing the business' case: in-scope patch,
    but it guts search functionality. CandidateValidator alone can't catch
    this -- it only checks file scope, not behavior. B's independent check
    suite must report a FAIL for this to be rejected."""

    def run_checks_reports_broken_search(candidate: Candidate) -> tuple[CheckResult, ...]:
        return (
            CheckResult(
                check_id="sqli-01",
                candidate_hash="",
                status=CheckStatus.PASS,
                observed_at=datetime.now(timezone.utc),
                artifact_ref=None,
                adapter_origin="semgrep",
            ),
            CheckResult(
                check_id="search.ordinary",
                candidate_hash="",
                status=CheckStatus.FAIL,
                observed_at=datetime.now(timezone.utc),
                artifact_ref=None,
                adapter_origin="behavior-suite",
                detail="search now returns an empty constant for all queries",
            ),
        )

    overbroad_patch = diff(ALLOWED_PATH, old="old", new="return []; // disabled search entirely")
    validator = CandidateValidator(allowed_paths=(ALLOWED_PATH,), expected_base_commit=BASE_COMMIT)
    agent = RepairAgent(
        run_id="r1",
        base_commit=BASE_COMMIT,
        patch_adapter=SupplierAdapter(overbroad_patch),
        validator=validator,
        run_checks=run_checks_reports_broken_search,
        source_files=SOURCE,
    )

    # Scope check alone passes -- the candidate only touches the allowed file.
    assert validator.validate(
        Candidate(
            candidate_id="probe",
            run_id="r1",
            base_commit=BASE_COMMIT,
            patch=overbroad_patch,
            content_hash="",
            origin="operator-supplied-bad-candidate",
        )
    )

    with pytest.raises(MaxAttemptsExceeded):
        agent.attempt_repair(make_finding())

    with pytest.raises(RuntimeError, match="no passing candidate"):
        agent.request_deploy("sha256:deadbeef")


def test_disclosed_origin_is_preserved_not_misattributed_to_the_model() -> None:
    bad_patch = diff("config/semgrep/rules.lock.json")
    validator = CandidateValidator(allowed_paths=(ALLOWED_PATH,), expected_base_commit=BASE_COMMIT)
    adapter = SupplierAdapter(bad_patch)

    candidate = adapter.propose(
        run_id="r1", base_commit=BASE_COMMIT, finding=make_finding(), source_files=SOURCE
    )

    assert candidate.origin == "operator-supplied-bad-candidate"
    with pytest.raises(Exception):
        validator.validate(candidate)
