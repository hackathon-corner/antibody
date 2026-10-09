"""Bounded repair loop (A5) and gated deploy request (A6).

The agent proposes, the host validates (validator.py) and runs B's
independent checks, and only a candidate that passed every required
check may be submitted for deployment -- enforced here regardless of
what the agent requests.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from adapters.base import PatchAdapter
from contracts import Candidate, CheckResult, CheckStatus, DeployRequest, Event

from .validator import CandidateValidator, ValidationError

MAX_ATTEMPTS = 2
EMITTER = "repair-agent"


class EventSink(Protocol):
    """Host-provided event emission. Default is a no-op so RepairAgent
    stays usable without a wired evidence pipeline (e.g. in tests)."""

    def emit(self, event: Event) -> None: ...


class _NullEventSink:
    def emit(self, event: Event) -> None:
        pass


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
        event_sink: EventSink | None = None,
    ) -> None:
        """run_checks is B's isolated worker entry point (B4); it returns
        the actual CheckResult set for a validated candidate hash."""
        self._run_id = run_id
        self._base_commit = base_commit
        self._patch_adapter = patch_adapter
        self._validator = validator
        self._run_checks = run_checks
        self._event_sink = event_sink or _NullEventSink()
        self._last_passing: Candidate | None = None
        self._last_passing_hash: str | None = None

    def _emit(self, event_type: str, outcome: str, candidate_hash: str | None = None, detail: str | None = None) -> None:
        self._event_sink.emit(
            Event(
                event_id=str(uuid.uuid4()),
                run_id=self._run_id,
                candidate_hash=candidate_hash,
                release_ref=None,
                event_type=event_type,
                emitter=EMITTER,
                observed_at=datetime.now(timezone.utc),
                outcome=outcome,
                detail=detail,
            )
        )

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
            self._emit("candidate.proposed", "proposed", detail=f"attempt {attempt}, origin={candidate.origin}")

            try:
                content_hash = self._validator.validate(candidate)
            except ValidationError as exc:
                # A rejected-before-build candidate still counts against
                # the attempt budget; it is a real outcome, not a retry-free skip.
                self._emit("candidate.rejected", "rejected", detail=str(exc))
                continue

            results = self._run_checks(candidate)
            passed = all(r.status == CheckStatus.PASS for r in results)
            self._emit(
                "checks.completed",
                "pass" if passed else "fail",
                candidate_hash=content_hash,
                detail=f"{sum(1 for r in results if r.status == CheckStatus.PASS)}/{len(results)} passed",
            )
            if passed:
                self._last_passing = candidate
                self._last_passing_hash = content_hash
                return candidate

        raise MaxAttemptsExceeded(f"no passing candidate for run {self._run_id} after {MAX_ATTEMPTS} attempts")

    def request_deploy(self, built_image_digest: str) -> DeployRequest:
        """Only the candidate that actually passed attempt_repair's checks
        may be submitted for deployment. Raises if called out of order."""
        if self._last_passing is None or self._last_passing_hash is None:
            raise RuntimeError("no passing candidate on record; refusing to request deploy")

        self._emit("deploy.requested", "requested", candidate_hash=self._last_passing_hash, detail=built_image_digest)

        return DeployRequest(
            run_id=self._run_id,
            candidate_hash=self._last_passing_hash,
            built_image_digest=built_image_digest,
        )
