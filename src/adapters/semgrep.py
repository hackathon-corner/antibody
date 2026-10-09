"""Semgrep scanner adapter.

Runs the real `semgrep` CLI against a pinned rule set. No network vendor
account is required -- this is the open-source CLI. Fails loudly if the
binary or config is missing rather than returning a synthesized result.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from contracts import CheckResult, CheckStatus


class SemgrepScanError(RuntimeError):
    """Raised when the scanner cannot be trusted to have run cleanly."""


class SemgrepAdapter:
    def __init__(self, config_path: str, binary: str = "semgrep") -> None:
        self._config_path = config_path
        self._binary = binary

    def scan(self, source_path: str, rule_ids: tuple[str, ...]) -> tuple[CheckResult, ...]:
        """Run the pinned rule set against source_path.

        Raises SemgrepScanError on a nonzero exit that is not "findings
        present" (semgrep exits 1 when findings exist, which is expected).
        """
        proc = subprocess.run(
            [self._binary, "scan", "--config", self._config_path, "--json", source_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode not in (0, 1):
            raise SemgrepScanError(
                f"semgrep exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
            )

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SemgrepScanError(f"semgrep did not return valid JSON: {exc}") from exc

        if payload.get("errors"):
            raise SemgrepScanError(f"semgrep reported scan errors: {payload['errors']}")

        results = payload.get("results", [])
        now = datetime.now(timezone.utc)

        checks: list[CheckResult] = []
        for rule_id in rule_ids:
            matches = [r for r in results if r.get("check_id") == rule_id]
            status = CheckStatus.FAIL if matches else CheckStatus.PASS
            # FAIL here means "rule matched" i.e. the defect is present;
            # the agent loop interprets baseline-FAIL vs candidate-PASS.
            detail = (
                f"{len(matches)} match(es) at "
                + ", ".join(f"{m['path']}:{m['start']['line']}" for m in matches)
                if matches
                else None
            )
            checks.append(
                CheckResult(
                    check_id=rule_id,
                    candidate_hash="",  # filled in by the caller once known
                    status=status,
                    observed_at=now,
                    artifact_ref=None,
                    adapter_origin="semgrep",
                    detail=detail,
                )
            )

        return tuple(checks)
