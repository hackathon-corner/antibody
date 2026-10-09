"""One repair run end to end, through the host runner (owner: C; Q13 in docs/collab.md).

    python scripts/target.py source --out runtime/source          # pinned source, once
    python scripts/run_repair.py --source runtime/source           # Guild proposes the candidate
    python scripts/run_repair.py --source runtime/source \\
        --supplied-patch tests/fixtures/juice-shop/candidates/mutant-where-1-0.patch \\
        --origin operator-supplied-bad-candidate                   # same gate, disclosed origin
    add --no-deploy to stop at ready_to_deploy (recorded as unresolved, never as success)

Chain: pinned Semgrep rule -> Senso guidance -> Guild (or a supplied patch) -> host validator ->
B's isolated worker (build + independent checks) -> upstream-answer match -> B's Akash connector ->
external probes -> ClickHouse events. Every stage's real outcome is recorded; nothing is substituted.

Needs on the machine that runs it: Docker (linux/amd64 images for Akash), the `semgrep`, `senso`
and `guild` CLIs signed in, `docker login ghcr.io` with write:packages, and in the environment or
.env: CLICKHOUSE_* (read-write app user), AKASH_API_KEY, GUILD_WORKSPACE, GUILD_AGENT_DIR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adapters.clickhouse_events import ClickHouseEventStore, load_settings, stable_event_id  # noqa: E402
from agent import CandidateValidator, RepairAgent  # noqa: E402
from contracts import Candidate, Event  # noqa: E402
from server.answer_match import compare  # noqa: E402
from server.runner import HostRunner, RunStore  # noqa: E402


def env_value(key: str) -> str | None:
    if os.environ.get(key):
        return os.environ[key]
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip() or None
    return None


def fetch_pinned_rule(dest: Path) -> tuple[str, Path]:
    lock = json.loads((ROOT / "config" / "semgrep" / "rules.lock.json").read_text())
    rule = lock["rules"][0]
    with urllib.request.urlopen(rule["url"], timeout=60) as r:
        body = r.read()
    got = hashlib.sha256(body).hexdigest()
    if got != rule["sha256"]:
        raise SystemExit(f"pinned Semgrep rule changed upstream: got {got}, lock wants {rule['sha256']}")
    path = dest / "rule.yaml"
    path.write_bytes(body)
    return rule["id"], path


class SuppliedPatch:
    """A patch supplied by an operator, labelled with its true origin. Never attributed to the model."""

    def __init__(self, patch: str, origin: str) -> None:
        self._patch, self._origin = patch, origin

    def propose(self, run_id, base_commit, finding, source_files, guidance_ids=(), attempt_number=1) -> Candidate:
        return Candidate(f"cand_{attempt_number}_{hashlib.sha256(self._patch.encode()).hexdigest()[:12]}",
                         run_id, base_commit, self._patch, "", self._origin, tuple(guidance_ids), attempt_number)


class RecordingProposer:
    """Wraps the patch adapter so the runner can see what was actually proposed."""

    def __init__(self, inner) -> None:
        self.inner, self.proposed = inner, []

    def propose(self, *args, **kwargs) -> Candidate:
        c = self.inner.propose(*args, **kwargs)
        self.proposed.append(c)
        return c


class Repairer:
    """Adapts RepairAgent to the runner, and records the upstream-answer match for the passing candidate."""

    def __init__(self, agent: RepairAgent, proposer: RecordingProposer, sink, run_id: str, source: Path, path: str):
        self.agent, self.proposer, self.sink, self.run_id, self.source, self.path = agent, proposer, sink, run_id, source, path

    def attempt_repair(self, finding, guidance_ids=()):
        candidate = self.agent.attempt_repair(finding, guidance_ids)
        self._answer_match(candidate)
        return candidate

    def request_deploy(self, digest):
        return self.agent.request_deploy(digest)

    def _answer_match(self, candidate: Candidate) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / self.path
            target.parent.mkdir(parents=True)
            shutil.copy(self.source / self.path, target)
            applied = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], cwd=tmp, input=candidate.patch,
                                     text=True, capture_output=True)
            if applied.returncode != 0:
                outcome, detail = "error", {"error": applied.stderr.strip()[:300]}
            else:
                matches = compare(target.read_text(), self.source / "data" / "static" / "codefixes")
                exact = [m.reference for m in matches if m.exact]
                outcome = "matches-upstream-answer" if exact else "no-exact-match"
                detail = {"exact": exact, "best": matches[0].reference, "similarity": matches[0].similarity}
        digest = hashlib.sha256(candidate.patch.encode()).hexdigest()
        self.sink.emit(Event(stable_event_id(self.run_id, "answer.match", "host-runner", digest), self.run_id, digest, None,
                             "answer.match", "host-runner", datetime.now(timezone.utc), outcome,
                             detail=json.dumps({**detail, "origin": candidate.origin})))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="pinned source tree from scripts/target.py source")
    ap.add_argument("--supplied-patch", help="operator-supplied patch instead of Guild")
    ap.add_argument("--origin", default="operator-supplied", help="true origin label for --supplied-patch")
    ap.add_argument("--no-deploy", action="store_true")
    ap.add_argument("--state", default=str(ROOT / "runtime" / "host.db"))
    args = ap.parse_args()

    target = json.loads((ROOT / "config" / "targets" / "juice-shop.json").read_text())
    source = Path(args.source).resolve()
    path = target["allowed_paths"][0]
    commit = target["source"]["commit"]
    if not (source / path).is_file():
        raise SystemExit(f"{source / path} not found; run scripts/target.py source first")
    if args.supplied_patch and args.origin in ("guild", "guild-agent", "model"):
        raise SystemExit("a supplied patch cannot be labelled as model output")

    load_settings()  # fail fast on missing ClickHouse settings
    sink = ClickHouseEventStore.from_env()
    sink.ensure_schema()
    runner = HostRunner(RunStore(args.state), sink)

    with tempfile.TemporaryDirectory() as tmp:
        rule_id, rule_path = fetch_pinned_rule(Path(tmp))
        from adapters.semgrep import SemgrepAdapter
        from adapters.check_worker import load_worker

        worker = load_worker()
        run = runner.create_run(target["target_id"], commit, target["baseline_image_digest"], tuple(target["allowed_paths"]),
                                (rule_id,), target["check_suite"]["sha256"])
        print(f"run {run.run_id}", flush=True)

        guidance: tuple[str, ...] = ()
        if args.supplied_patch:
            proposer = RecordingProposer(SuppliedPatch(Path(args.supplied_patch).read_text(), args.origin))
        else:
            from adapters.guild import GuildPatchAdapter
            from adapters.senso import SensoGuidanceAdapter

            guidance = SensoGuidanceAdapter().retrieve(
                "How do I pass user input to sequelize.query safely in a LIKE clause instead of string interpolation?")
            proposer = RecordingProposer(GuildPatchAdapter(env_value("GUILD_WORKSPACE") or "", env_value("GUILD_AGENT_DIR") or ""))

        agent = RepairAgent(run.run_id, commit, proposer, CandidateValidator(tuple(target["allowed_paths"]), commit),
                            worker.run_checks, {path: (source / path).read_text()}, event_sink=sink)
        connector = None
        if not args.no_deploy:
            from adapters.akash_deploy import load_connector
            connector = load_connector()
        # Scan the allowed file itself: Semgrep skips git-ignored trees (runtime/ is ignored) and then
        # reports 0 files scanned as a clean result.
        final = runner.execute(run.run_id, str(source / path), SemgrepAdapter(str(rule_path)),
                               Repairer(agent, proposer, sink, run.run_id, source, path),
                               worker.build_candidate, connector, guidance)

    print(json.dumps({"runId": final.run_id, "state": final.state.value,
                      "candidates": [{"id": c.candidate_id, "origin": c.origin} for c in proposer.proposed]}, indent=2))
    sys.exit(0 if final.state.value == "completed" else 1)


if __name__ == "__main__":
    main()
