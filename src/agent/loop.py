"""Bounded repair loop (A5) and gated deploy request (A6).

The agent proposes, the host validates (validator.py) and runs B's
independent checks, and only a candidate that passed every required
check may be submitted for deployment -- enforced here regardless of
what the agent requests.
"""

from __future__ import annotations

from collections.abc import Callable

from adapters.base import PatchAdapter
from contracts import Candidate, CheckResult, CheckStatus, DeployRequest

from .validator import CandidateValidator, ValidationError

MAX_ATTEMPTS = 2


class MaxAttemptsExceeded(RuntimeError):
    """Raised when no passing candidate was found within MAX_ATTEMPTS."""


class RepairAgent:
    def __init__(
        self,
        run_id: str,
        base_commit: str,
        patch_adapter: PatchAdapter,
        validator: CandidateValidator,
        run_checks: Callable[[Candidate], tuple[CheckResult, ...]],
    ) -> None:
        """run_checks is B's isolated worker entry point (B4); it returns
        the actual CheckResult set for a validated candidate hash."""
        self._run_id = run_id
        self._base_commit = base_commit
        self._patch_adapter = patch_adapter
        self._validator = validator
        self._run_checks = run_checks
        self._last_passing: Candidate | None = None
        self._last_passing_hash: str | None = None

    def attempt_repair(self, finding: CheckResult, guidance_ids: tuple[str, ...] = ()) -> Candidate:
        """Propose and validate candidates until one passes all checks or
        MAX_ATTEMPTS is exhausted. Returns the passing candidate.

        Raises MaxAttemptsExceeded if no candidate passes.
        """
        for attempt in range(1, MAX_ATTEMPTS + 1):
            candidate = self._patch_adapter.propose(
                run_id=self._run_id,
                base_commit=self._base_commit,
                finding=finding,
                guidance_ids=guidance_ids,
                attempt_number=attempt,
            )

            try:
                content_hash = self._validator.validate(candidate)
            except ValidationError:
                # A rejected-before-build candidate still counts against
                # the attempt budget; it is a real outcome, not a retry-free skip.
                continue

            results = self._run_checks(candidate)
            if all(r.status == CheckStatus.PASS for r in results):
                self._last_passing = candidate
                self._last_passing_hash = content_hash
                return candidate

        raise MaxAttemptsExceeded(f"no passing candidate for run {self._run_id} after {MAX_ATTEMPTS} attempts")

    def request_deploy(self, built_image_digest: str) -> DeployRequest:
        """Only the candidate that actually passed attempt_repair's checks
        may be submitted for deployment. Raises if called out of order."""
        if self._last_passing is None or self._last_passing_hash is None:
            raise RuntimeError("no passing candidate on record; refusing to request deploy")

        return DeployRequest(
            run_id=self._run_id,
            candidate_hash=self._last_passing_hash,
            built_image_digest=built_image_digest,
        )
