import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from adapters.check_worker import CheckWorker, CommandResult, patch_paths, suite_hash
from contracts import Candidate, CheckStatus

TARGET = {
    "target_id": "juice-shop",
    "allowed_paths": ["routes/search.ts"],
    "base_images": {"build": "node:24@sha256:abc"},
}
GOOD_PATCH = """diff --git a/routes/search.ts b/routes/search.ts
--- a/routes/search.ts
+++ b/routes/search.ts
@@ -1 +1 @@
-old
+new
"""
IMAGE = "sha256:" + "e" * 64


def candidate(patch=GOOD_PATCH, claimed=None):
    h = hashlib.sha256(patch.encode()).hexdigest()
    return Candidate("c1", "run1", "5658473c", patch, claimed or h, "test-fixture")


def suite_report(worker, overall="pass", outcomes=None, mode="candidate", sha=None):
    outcomes = outcomes or {"setup.canary-user": "pass", "search.ordinary": "pass", "security.injection": "pass"}
    return json.dumps({
        "suite": {"id": "juice-shop-checks", "sha256": sha or worker.suite_hash},
        "mode": mode, "overall": overall,
        "results": [{"checkId": k, "required": True, "outcome": v, "observed": {"n": 1}} for k, v in outcomes.items()],
    })


class FakeDocker:
    """Records commands; answers build, docker and suite calls from a script."""

    def __init__(self, runtime, build_rc=0, suite=None, fail_on=None, timeout_on=None):
        self.runtime, self.build_rc, self.suite, self.fail_on, self.timeout_on = runtime, build_rc, suite, fail_on, timeout_on
        self.calls = []

    def __call__(self, cmd, timeout):
        self.calls.append(cmd)
        joined = " ".join(cmd)
        if self.timeout_on and self.timeout_on in joined:
            raise subprocess.TimeoutExpired(cmd, timeout)
        if "target.py" in joined:
            if self.build_rc == 0:
                patch = Path(cmd[-1]).read_bytes()
                h = hashlib.sha256(patch).hexdigest()
                (self.runtime / "builds").mkdir(parents=True, exist_ok=True)
                (self.runtime / "builds" / f"{h[:12]}.json").write_text(json.dumps({"candidate_hash": h, "image_id": IMAGE}))
            return CommandResult(self.build_rc, "", "error: patch does not apply" if self.build_rc else "")
        if self.fail_on and self.fail_on in joined:
            return CommandResult(1, "", "boom")
        if "--entrypoint" in cmd:
            return self.suite
        return CommandResult(0, "", "")


@pytest.fixture
def make(tmp_path):
    def _make(**kw):
        fake = FakeDocker(tmp_path, **kw)
        worker = CheckWorker(TARGET, runner=fake, runtime_dir=tmp_path)
        return worker, fake
    return _make


def test_passing_candidate_binds_hash_image_and_suite(make):
    worker, fake = make()
    fake.suite = CommandResult(0, suite_report(worker), "")
    c = candidate()
    results = worker.run_checks(c)
    assert [r.check_id for r in results] == ["behavior.setup.canary-user", "behavior.search.ordinary", "behavior.security.injection"]
    assert all(r.status == CheckStatus.PASS for r in results)
    assert {(r.candidate_hash, r.image_digest, r.suite_hash) for r in results} == {(c.content_hash, IMAGE, worker.suite_hash)}
    assert worker.build_candidate(c) == IMAGE


def test_target_isolated_and_suite_read_only(make):
    worker, fake = make()
    fake.suite = CommandResult(0, suite_report(worker), "")
    worker.run_checks(candidate())
    net = next(c for c in fake.calls if c[1:3] == ["network", "create"])
    assert "--internal" in net
    target_run = next(c for c in fake.calls if c[1:3] == ["run", "-d"])
    assert IMAGE in target_run and "-p" not in target_run and "--publish" not in target_run
    assert {"--cap-drop", "--memory", "--cpus", "--pids-limit"} <= set(target_run)
    suite_run = next(c for c in fake.calls if "--entrypoint" in c)
    assert all(m.endswith(",readonly") for m in (suite_run[i + 1] for i, a in enumerate(suite_run) if a == "--mount"))
    assert any(c[1:3] == ["rm", "-f"] for c in fake.calls) and any(c[1:3] == ["network", "rm"] for c in fake.calls)


@pytest.mark.parametrize("patch", [
    GOOD_PATCH.replace("routes/search.ts", "test/api/searchApiSpec.ts"),
    GOOD_PATCH + "diff --git a/package.json b/package.json\n--- a/package.json\n+++ b/package.json\n@@ -1 +1 @@\n-a\n+b\n",
    "diff --git a/routes/search.ts b/routes/search.ts\nrename from routes/search.ts\nrename to routes/other.ts\n",
    "diff --git a/lib/insecurity.ts b/lib/insecurity.ts\ndeleted file mode 100644\n--- a/lib/insecurity.ts\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n",
    "diff --git a/routes/search.ts b/routes/search.ts\nGIT binary patch\nliteral 0\n",
    "",
])
def test_out_of_scope_rejected_before_build(make, patch):
    worker, fake = make()
    results = worker.run_checks(candidate(patch))
    assert [(r.check_id, r.status) for r in results] == [("worker.scope", CheckStatus.FAIL)]
    assert fake.calls == []


def test_claimed_hash_mismatch_is_error_and_not_built(make):
    worker, fake = make()
    results = worker.run_checks(candidate(claimed="0" * 64))
    assert results[0].check_id == "worker.identity" and results[0].status == CheckStatus.ERROR
    assert fake.calls == []


def test_build_failure_fails_and_blocks_deploy(make):
    worker, _ = make(build_rc=1)
    c = candidate()
    results = worker.run_checks(c)
    assert [(r.check_id, r.status) for r in results] == [("worker.build", CheckStatus.FAIL)]
    with pytest.raises(RuntimeError, match="no verification record"):
        worker.build_candidate(c)


def test_build_timeout_is_error(make):
    worker, _ = make(timeout_on="target.py")
    assert worker.run_checks(candidate())[0].status == CheckStatus.ERROR


def test_failing_check_blocks_deploy(make):
    worker, fake = make()
    fake.suite = CommandResult(1, suite_report(worker, "fail", {"search.ordinary": "fail", "security.injection": "pass"}), "")
    c = candidate()
    results = worker.run_checks(c)
    assert [r.status for r in results] == [CheckStatus.FAIL, CheckStatus.PASS]
    with pytest.raises(RuntimeError, match="did not pass"):
        worker.build_candidate(c)


@pytest.mark.parametrize("suite,why", [
    (CommandResult(2, "not json", "crash"), "not JSON"),
    (CommandResult(3, "", "target not ready"), "readiness"),
    (CommandResult(0, None, ""), "disagrees"),  # filled below: overall fail with exit 0
    (CommandResult(0, None, ""), "worker expects"),  # filled below: wrong suite hash
    (CommandResult(0, None, ""), "mode"),  # filled below: baseline mode
])
def test_suite_anomalies_are_errors(make, suite, why):
    worker, fake = make()
    if suite.stdout is None:
        body = {"disagrees": suite_report(worker, overall="fail"),
                "worker expects": suite_report(worker, sha="f" * 64),
                "mode": suite_report(worker, mode="baseline")}[why]
        suite = CommandResult(0, body, "")
    fake.suite = suite
    c = candidate()
    results = worker.run_checks(c)
    assert len(results) == 1 and results[0].status == CheckStatus.ERROR and why in results[0].detail
    with pytest.raises(RuntimeError):
        worker.build_candidate(c)


def test_unknown_outcome_never_passes(make):
    worker, fake = make()
    fake.suite = CommandResult(0, suite_report(worker, outcomes={"search.ordinary": "observed"}), "")
    assert worker.run_checks(candidate())[0].status == CheckStatus.UNKNOWN


def test_isolation_failure_is_error_and_cleans_up(make):
    worker, fake = make(fail_on="network create")
    results = worker.run_checks(candidate())
    assert results[0].check_id == "worker.isolation" and results[0].status == CheckStatus.ERROR
    assert not any("--entrypoint" in c for c in fake.calls)
    assert any(c[1:3] == ["network", "rm"] for c in fake.calls)


def test_rerun_after_failure_clears_stale_pass(make):
    worker, fake = make()
    fake.suite = CommandResult(0, suite_report(worker), "")
    c = candidate()
    worker.run_checks(c)
    fake.build_rc = 1
    worker.run_checks(c)
    with pytest.raises(RuntimeError):
        worker.build_candidate(c)


def test_suite_hash_matches_node_construction(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"one")
    b.write_bytes(b"two")
    inner = "\n".join(hashlib.sha256(x).hexdigest() for x in (b"one", b"two"))
    assert suite_hash((a, b)) == hashlib.sha256(inner.encode()).hexdigest()


def test_patch_paths_strips_timestamps():
    assert patch_paths("--- a/routes/search.ts\t2026-10-09\n+++ b/routes/search.ts\t2026-10-09\n") == {"routes/search.ts"}
