"""Adapter interfaces. Each provider gets a narrow, swappable boundary.

An adapter returns real provider output or raises; it never fabricates a
result to keep a run moving. Adapters hold no deploy/ClickHouse/host
secrets -- only the credentials needed for their own provider call.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from contracts import Candidate, CheckResult


class ScannerAdapter(Protocol):
    """Runs a pinned static-analysis rule set against a source revision."""

    def scan(self, source_path: str, rule_ids: tuple[str, ...]) -> tuple[CheckResult, ...]:
        """Return one CheckResult per rule_id actually evaluated."""
        ...


class PatchAdapter(Protocol):
    """Proposes a candidate patch via an agent runtime (e.g. Guild)."""

    def propose(
        self,
        run_id: str,
        base_commit: str,
        finding: CheckResult,
        source_files: Mapping[str, str],
        guidance_ids: tuple[str, ...] = (),
        attempt_number: int = 1,
    ) -> Candidate:
        """Return a candidate with content_hash left unset -- the host computes it.

        source_files maps allowed repo-relative path -> full file content at
        base_commit. This is the agent's entire view of the repo -- it
        receives no filesystem or network access, so anything not in this
        map (e.g. data/static/codefixes/) is simply never in its context.
        """
        ...


class GuidanceAdapter(Protocol):
    """Retrieves source-linked remediation guidance (e.g. Senso)."""

    def retrieve(self, query: str) -> tuple[str, ...]:
        """Return guidance IDs/passages actually retrieved, not inferred."""
        ...
