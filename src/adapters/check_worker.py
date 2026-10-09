"""Isolated candidate verification worker (B4). Owner: B.

Two entry points:

- ``run_checks(candidate)`` for A's ``RepairAgent``: checks scope independently,
  builds the candidate through ``scripts/target.py build``, runs the B3 suite in
  candidate mode against that exact image, and returns ``CheckResult`` rows bound
  to the candidate hash, image ID and suite hash.
- ``build_candidate(candidate)`` for C's ``HostRunner``: returns the image ID that
  ``run_checks`` verified for this candidate. It never builds; an unverified,
  failed or stale candidate raises.

Isolation: the target container runs on a per-check ``--internal`` Docker network
(no egress, no published ports) with CPU, memory and pid limits and all
capabilities dropped. The suite runs in a pinned Node container on the same
network, with the suite and fixtures bind-mounted read-only from this host
checkout, never from the candidate. Subprocesses get an allowlisted environment,
so no vendor or deploy secrets reach the build or the checks.

Errors, timeouts and unparseable output become ``CheckStatus.ERROR`` rows. They
never pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from contracts import Candidate, CheckResult, CheckStatus

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "behavior-suite"
SUITE_FILE = ROOT / "tests" / "e2e" / "juice-shop-checks.mjs"
FIXTURE_FILE = ROOT / "tests" / "fixtures" / "juice-shop" / "search-expectations.json"

# Variables a docker/python subprocess needs to work on Windows and Linux. Nothing else is passed.
_ENV_ALLOW = (
    "PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "ProgramData", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
)

_DIFF_PATHS = re.compile(r"^(?:\+\+\+ b/|--- a/|rename from |rename to |copy from |copy to )(.+)$", re.MULTILINE)
_GIT_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)

_STATUS = {"pass": CheckStatus.PASS, "fail": CheckStatus.FAIL, "error": CheckStatus.ERROR}

# Waits for the target, then runs the suite. Exit 3 = target never answered.
_SUITE_SCRIPT = (
    'URL=http://target:3000; i=0; '
    'until node -e "fetch(process.argv[1]).then(r=>process.exit(r.ok?0:1),()=>process.exit(1))" '
    '"$URL/rest/admin/application-version"; do '
    'i=$((i+1)); if [ $i -ge {tries} ]; then echo "target not ready" >&2; exit 3; fi; sleep 2; done; '
    'exec node /suite/e2e/juice-shop-checks.mjs --base-url "$URL" --mode candidate'
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], float], CommandResult]


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k in _ENV_ALLOW}


def _subprocess_runner(cmd: list[str], timeout: float) -> CommandResult:
    """Raises subprocess.TimeoutExpired on timeout; callers turn that into ERROR."""
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env=_clean_env(), cwd=ROOT)
    return CommandResult(p.returncode, p.stdout, p.stderr)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def suite_hash(files: tuple[Path, ...] = (SUITE_FILE, FIXTURE_FILE)) -> str:
    """Same construction as juice-shop-checks.mjs: sha256 over the newline-joined file hashes."""
    return sha256_hex("\n".join(sha256_hex(f.read_bytes()) for f in files).encode("utf-8"))


def patch_paths(patch: str) -> frozenset[str]:
    """Every path a unified/git diff names, including deletions, renames and copies."""
    paths = {p.split("\t", 1)[0].strip() for p in _DIFF_PATHS.findall(patch)}
    for a, b in _GIT_HEADER.findall(patch):
        paths.update((a, b))
    paths.discard("/dev/null")
    return frozenset(paths)


class CheckWorker:
    def __init__(self, target: dict, *, runner: CommandRunner | None = None, runtime_dir: Path | None = None,
                 docker: str = "docker", build_timeout: float = 1800, suite_timeout: float = 420,
                 ready_tries: int = 90) -> None:
        self._target = target
        self._allowed = frozenset(target["allowed_paths"])
        self._node_image = target["base_images"]["build"]
        self._run = runner or _subprocess_runner
        self._runtime = runtime_dir or ROOT / "runtime"
        self._docker = docker
        self._build_timeout = build_timeout
        self._suite_timeout = suite_timeout
        self._ready_tries = ready_tries
        self.suite_hash = suite_hash()

    # ---- A's RepairAgent entry point -------------------------------------------------------

    def run_checks(self, candidate: Candidate) -> tuple[CheckResult, ...]:
        patch = candidate.patch.encode("utf-8")
        h = sha256_hex(patch)

        def result(check_id: str, status: CheckStatus, detail: str, image: str | None = None,
                   artifact: str | None = None) -> CheckResult:
            return CheckResult(check_id, h, status, datetime.now(timezone.utc), artifact, ORIGIN,
                               detail=detail[:2000], image_digest=image, suite_hash=self.suite_hash)

        if h != candidate.content_hash:
            return (result("worker.identity", CheckStatus.ERROR,
                           f"patch hashes to {h}, candidate claims {candidate.content_hash}"),)
        problem = self._scope_problem(candidate.patch)
        if problem:
            return (result("worker.scope", CheckStatus.FAIL, problem),)

        work = self._runtime / "checks" / h[:12]
        work.mkdir(parents=True, exist_ok=True)
        (work / "result.json").unlink(missing_ok=True)
        patch_file = work / "candidate.patch"
        patch_file.write_bytes(patch)

        image, build_error = self._build(h, patch_file, work)
        if build_error:
            return (result("worker.build", *build_error, artifact=self._rel(work / "build.log")),)

        results = self._run_suite(h, image, work, result)
        passed = bool(results) and all(r.status == CheckStatus.PASS for r in results)
        (work / "result.json").write_text(json.dumps({
            "candidate_hash": h, "image_id": image, "suite_hash": self.suite_hash, "passed": passed,
            "results": {r.check_id: r.status.value for r in results},
        }, indent=2), encoding="utf-8")
        return results

    # ---- C's HostRunner entry point --------------------------------------------------------

    def build_candidate(self, candidate: Candidate) -> str:
        h = sha256_hex(candidate.patch.encode("utf-8"))
        record_path = self._runtime / "checks" / h[:12] / "result.json"
        if not record_path.exists():
            raise RuntimeError(f"candidate {h[:12]} has no verification record; run_checks first")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("candidate_hash") != h:
            raise RuntimeError(f"verification record belongs to {record.get('candidate_hash')}, not {h}")
        if not record.get("passed"):
            raise RuntimeError(f"candidate {h[:12]} did not pass the required checks")
        if record.get("suite_hash") != self.suite_hash:
            raise RuntimeError("check suite changed since this candidate was verified; re-run checks")
        return record["image_id"]

    # ---- internals -------------------------------------------------------------------------

    def _scope_problem(self, patch: str) -> str | None:
        if "GIT binary patch" in patch or re.search(r"^Binary files ", patch, re.MULTILINE):
            return "binary patches are not allowed"
        paths = patch_paths(patch)
        if not paths:
            return "patch names no files"
        forbidden = sorted(paths - self._allowed)
        if forbidden:
            return f"patch touches paths outside {sorted(self._allowed)}: {forbidden}"
        return None

    def _build(self, h: str, patch_file: Path, work: Path) -> tuple[str | None, tuple[CheckStatus, str] | None]:
        cmd = [sys.executable, str(ROOT / "scripts" / "target.py"), "--target", self._target["target_id"],
               "build", "--patch", str(patch_file)]
        try:
            out = self._run(cmd, self._build_timeout)
        except subprocess.TimeoutExpired:
            return None, (CheckStatus.ERROR, f"build exceeded {self._build_timeout:.0f}s")
        except OSError as exc:
            return None, (CheckStatus.ERROR, f"build could not start: {exc}")
        (work / "build.log").write_text(out.stdout + "\n--- stderr ---\n" + out.stderr, encoding="utf-8")
        if out.returncode != 0:
            tail = out.stderr.strip().splitlines()[-5:]
            return None, (CheckStatus.FAIL, "candidate build failed: " + " | ".join(tail))

        record_path = self._runtime / "builds" / f"{h[:12]}.json"
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return None, (CheckStatus.ERROR, f"build record unreadable: {exc}")
        if record.get("candidate_hash") != h or not str(record.get("image_id", "")).startswith("sha256:"):
            return None, (CheckStatus.ERROR, f"build record does not match candidate {h[:12]}")
        return record["image_id"], None

    def _run_suite(self, h: str, image: str, work: Path, result) -> tuple[CheckResult, ...]:
        tag = f"antibody-check-{h[:12]}-{uuid.uuid4().hex[:6]}"
        d = self._docker
        hardening = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
        artifact = self._rel(work / "checks.json")
        try:
            steps = [
                ([d, "network", "create", "--internal", tag], 60),
                ([d, "run", "-d", "--name", tag, "--network", tag, "--network-alias", "target",
                  "--memory", "2g", "--cpus", "2", "--pids-limit", "1024", *hardening, image], 120),
            ]
            for cmd, timeout in steps:
                out = self._run(cmd, timeout)
                if out.returncode != 0:
                    return (result("worker.isolation", CheckStatus.ERROR,
                                   f"{' '.join(cmd[1:3])} failed: {out.stderr.strip()[-300:]}", image),)

            suite = self._run([
                d, "run", "--rm", "--network", tag, "--memory", "512m", "--cpus", "1", *hardening,
                "--mount", f"type=bind,src={SUITE_FILE.parent},dst=/suite/e2e,readonly",
                "--mount", f"type=bind,src={FIXTURE_FILE.parent},dst=/suite/fixtures/juice-shop,readonly",
                "--entrypoint", "sh", self._node_image, "-c", _SUITE_SCRIPT.replace("{tries}", str(self._ready_tries)),
            ], self._suite_timeout)
        except subprocess.TimeoutExpired:
            return (result("worker.suite", CheckStatus.ERROR, f"suite exceeded {self._suite_timeout:.0f}s", image),)
        except OSError as exc:
            return (result("worker.suite", CheckStatus.ERROR, f"docker could not start: {exc}", image),)
        finally:
            logs = self._safe([d, "logs", tag])
            if logs is not None:
                (work / "target.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
            self._safe([d, "rm", "-f", tag])
            self._safe([d, "network", "rm", tag])

        if suite.returncode == 3:
            return (result("worker.startup", CheckStatus.ERROR, "target did not answer before the readiness limit",
                           image, self._rel(work / "target.log")),)
        return self._parse(suite, image, work, artifact, result)

    def _parse(self, suite: CommandResult, image: str, work: Path, artifact: str, result) -> tuple[CheckResult, ...]:
        try:
            report = json.loads(suite.stdout)
        except ValueError:
            return (result("worker.suite", CheckStatus.ERROR,
                           f"suite exit {suite.returncode}, output not JSON: {suite.stderr.strip()[-300:]}", image),)
        (work / "checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

        if report.get("suite", {}).get("sha256") != self.suite_hash:
            return (result("worker.suite", CheckStatus.ERROR,
                           f"suite reported hash {report.get('suite', {}).get('sha256')}, worker expects {self.suite_hash}",
                           image, artifact),)
        if report.get("mode") != "candidate":
            return (result("worker.suite", CheckStatus.ERROR, f"suite ran in mode {report.get('mode')!r}", image, artifact),)
        expected_exit = {"pass": 0, "fail": 1, "error": 2}.get(report.get("overall"))
        if expected_exit != suite.returncode:
            return (result("worker.suite", CheckStatus.ERROR,
                           f"suite overall {report.get('overall')!r} disagrees with exit {suite.returncode}", image, artifact),)

        rows = [r for r in report.get("results", []) if r.get("required")]
        if not rows:
            return (result("worker.suite", CheckStatus.ERROR, "suite returned no required checks", image, artifact),)
        return tuple(
            result(f"behavior.{r.get('checkId')}", _STATUS.get(r.get("outcome"), CheckStatus.UNKNOWN),
                   json.dumps({"outcome": r.get("outcome"), "observed": r.get("observed")}), image, artifact)
            for r in rows
        )

    def _safe(self, cmd: list[str]) -> CommandResult | None:
        try:
            return self._run(cmd, 60)
        except (subprocess.TimeoutExpired, OSError):
            return None

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(ROOT).as_posix()
        except ValueError:
            return str(path)


def load_worker(target_id: str = "juice-shop", **kwargs) -> CheckWorker:
    target = json.loads((ROOT / "config" / "targets" / f"{target_id}.json").read_text(encoding="utf-8"))
    return CheckWorker(target, **kwargs)


__all__ = ["CheckWorker", "CommandResult", "load_worker", "patch_paths", "suite_hash"]
