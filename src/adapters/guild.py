"""Guild AI patch-proposal adapter.

No Guild account/session exists yet (A1 is not complete). This adapter
raises until real session wiring lands -- it must never return a
synthesized candidate standing in for an actual Guild tool call.
"""

from __future__ import annotations

from contracts import Candidate


class GuildNotConfiguredError(RuntimeError):
    """Raised until a real Guild session is authenticated and wired (A1)."""


class GuildPatchAdapter:
    def __init__(self, session_ref: str | None = None) -> None:
        self._session_ref = session_ref

    def propose(
        self,
        run_id: str,
        base_commit: str,
        finding,
        guidance_ids: tuple[str, ...] = (),
        attempt_number: int = 1,
    ) -> Candidate:
        if self._session_ref is None:
            raise GuildNotConfiguredError(
                "No authenticated Guild session (A1 incomplete). "
                "Refusing to fabricate a candidate."
            )
        raise NotImplementedError("Guild tool invocation pending A1/A3 completion.")
