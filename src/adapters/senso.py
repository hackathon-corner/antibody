"""Senso guidance-retrieval adapter (A7).

Shells out to the `senso` CLI, scoped to the pinned content IDs for this
project's repair guidance (see docs/collab.md Q11) so org-wide search
doesn't pull in unrelated documents, including the team's own shared-context
notes (Q12). Authenticates via SENSO_API_KEY in the environment, not an
interactive `senso login` session, so the adapter works wherever the host
runner actually executes, not just on the machine someone logged in from.

Retrieved guidance is advisory, never authoritative (PRD section 5/7):
the candidate's own validation and B's independent checks are what decide
correctness, not what this adapter returns.
"""

from __future__ import annotations

import json
import subprocess

# Pinned in docs/collab.md Q11: OWASP SQL Injection Prevention Cheat Sheet,
# Sequelize v6 Raw Queries. Update here if the pinned sources change.
DEFAULT_CONTENT_IDS: tuple[str, ...] = (
    "54036268-5be8-4cee-96e2-97e52ae95ab2",
    "2fc71565-db91-41a7-8c6d-f15b1abda7ed",
)


class SensoRetrievalError(RuntimeError):
    """Raised when retrieval cannot be trusted to have returned real results."""


class SensoGuidanceAdapter:
    def __init__(
        self,
        content_ids: tuple[str, ...] = DEFAULT_CONTENT_IDS,
        senso_binary: str = "senso",
        timeout: float = 30.0,
    ) -> None:
        self._content_ids = content_ids
        self._senso_binary = senso_binary
        self._timeout = timeout

    def retrieve(self, query: str) -> tuple[str, ...]:
        """Return source-tagged guidance strings, each prefixed with its
        content_id for traceability (e.g. "[54036268-...] <title>: <text>").
        Raises SensoRetrievalError rather than returning a guess on failure.
        """
        proc = subprocess.run(
            [
                self._senso_binary,
                "search",
                query,
                "--content-ids",
                *self._content_ids,
                "--require-scoped-ids",
                "--output",
                "json",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        if proc.returncode != 0:
            raise SensoRetrievalError(
                f"senso search exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
            )

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SensoRetrievalError(f"senso search did not return valid JSON: {exc}") from exc

        passages: list[str] = []
        answer = data.get("answer")
        if answer:
            passages.append(f"[synthesized] {answer}")

        for result in data.get("results", []):
            content_id = result.get("content_id")
            if not content_id:
                continue
            title = result.get("title", "")
            text = (
                result.get("chunk_text")
                or result.get("text")
                or result.get("snippet")
                or result.get("content")
                or ""
            )
            label = f"{title}: {text}" if text else title
            passages.append(f"[{content_id}] {label}")

        if not passages:
            raise SensoRetrievalError(f"senso search returned no results for query: {query!r}")

        return tuple(passages)
