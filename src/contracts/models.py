"""Shared typed contracts for the Antibody repair run.

Owner: A, with B/C review (see docs/PRD.md section 6). Do not change these
shapes unilaterally -- B's worker/connector and C's evidence API/report
depend on them matching exactly.

These are host-side data contracts, not provider SDK types. A model or
adapter may *propose* field values (e.g. a Candidate's patch); only the
host assigns identity fields like hashes and IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RunState(str, Enum):
    CREATED = "created"
    SCANNING = "scanning"
    PROPOSING = "proposing"
    VALIDATING = "validating"
    READY_TO_DEPLOY = "ready_to_deploy"
    DEPLOYING = "deploying"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    UNRESOLVED = "unresolved"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    UNKNOWN = "unknown"


class DeployStatus(str, Enum):
    ACCEPTED = "accepted"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Run:
    run_id: str
    target_id: str
    baseline_commit: str
    baseline_image_digest: str
    allowed_paths: tuple[str, ...]
    rule_ids: tuple[str, ...]
    test_suite_hash: str
    started_at: datetime
    state: RunState


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    run_id: str
    base_commit: str
    patch: str
    """Complete unified diff or full file replacement content, never a partial hunk."""
    content_hash: str
    """Host-computed hash of the patch; the model's claimed hash is never trusted."""
    origin: str
    """e.g. 'guild-agent', 'operator-supplied-bad-candidate' -- must be accurate."""
    linked_guidance_ids: tuple[str, ...] = field(default_factory=tuple)
    attempt_number: int = 1


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    candidate_hash: str
    status: CheckStatus
    observed_at: datetime
    artifact_ref: str | None
    """Reference to a redacted artifact (e.g. log excerpt), not raw output."""
    adapter_origin: str
    """Which adapter/provider produced this result, e.g. 'semgrep', 'behavior-suite'."""
    detail: str | None = None


@dataclass(frozen=True)
class DeployRequest:
    run_id: str
    candidate_hash: str
    built_image_digest: str


@dataclass(frozen=True)
class DeployResult:
    attempt_id: str
    target_id: str
    image_digest: str
    release_ref: str | None
    status: DeployStatus
    error: str | None = None


@dataclass(frozen=True)
class Observation:
    url: str
    target_id: str
    probe_id: str
    release_ref: str
    status_code: int
    body_digest: str
    observed_at: datetime
    redacted_result: str


@dataclass(frozen=True)
class Event:
    event_id: str
    run_id: str
    candidate_hash: str | None
    release_ref: str | None
    event_type: str
    emitter: str
    observed_at: datetime
    outcome: str
    artifact_ref: str | None = None


@dataclass(frozen=True)
class Report:
    schema_version: str
    run_id: str
    source_commit: str
    source_links: tuple[str, ...]
    checks: tuple[CheckResult, ...]
    observations: tuple[Observation, ...]
    candidate_origin: str
    exercised_sponsors: tuple[str, ...]
    limitations: str
    public_urls: tuple[str, ...]
