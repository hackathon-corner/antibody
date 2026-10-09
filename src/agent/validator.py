"""Host-side candidate validation (A4).

Independently recomputes a candidate's content hash and changed-file
scope from the actual patch text. Never trusts a model- or
adapter-claimed hash or path list. The agent cannot edit this module's
decisions at runtime -- it only sees pass/reject.
"""

from __future__ import annotations

import hashlib
import re

from contracts import Candidate

_DIFF_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


class ValidationError(RuntimeError):
    """Raised when a candidate is rejected. Message states the exact reason."""


class CandidateValidator:
    def __init__(self, allowed_paths: tuple[str, ...], expected_base_commit: str) -> None:
        self._allowed_paths = set(allowed_paths)
        self._expected_base_commit = expected_base_commit

    def compute_hash(self, patch: str) -> str:
        return hashlib.sha256(patch.encode("utf-8")).hexdigest()

    def changed_paths(self, patch: str) -> frozenset[str]:
        return frozenset(_DIFF_PATH_RE.findall(patch))

    def validate(self, candidate: Candidate) -> str:
        """Return the host-computed content hash, or raise ValidationError."""
        if candidate.base_commit != self._expected_base_commit:
            raise ValidationError(
                f"stale base commit: candidate based on {candidate.base_commit!r}, "
                f"expected {self._expected_base_commit!r}"
            )

        changed = self.changed_paths(candidate.patch)
        if not changed:
            raise ValidationError("patch declares no changed files; cannot validate scope")

        forbidden = changed - self._allowed_paths
        if forbidden:
            raise ValidationError(f"patch touches forbidden path(s): {sorted(forbidden)}")

        return self.compute_hash(candidate.patch)
