"""Guild AI patch-proposal adapter.

Guild's CLI has a known client-side quirk: `guild agent chat`/`guild agent
test` block on polling for a reply, but Guild's own message-accept step can
take 30-60s, which makes the CLI look hung even though the session is
progressing server-side (confirmed with Guild support, 2026-10-09). This
adapter works around it: launch `guild agent chat` only to create the
session and read its printed session ID from stdout, then poll
`guild session events --events all` independently until the agent's final
message appears. The original chat subprocess is terminated once we have
the session ID; it holds no information we still need.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from collections.abc import Mapping

from contracts import Candidate

_SESSION_ID_RE = re.compile(r"Session:\s*(\S+)")
_DIFF_FENCE_RE = re.compile(r"```diff\n(.*?)```", re.DOTALL)


class GuildNotConfiguredError(RuntimeError):
    """Raised when workspace/agent identifiers are missing."""


class GuildSessionTimeoutError(RuntimeError):
    """Raised when the session never produces a usable final message in time."""


class GuildResponseFormatError(RuntimeError):
    """Raised when the agent's final message has no extractable diff."""


class GuildPatchAdapter:
    def __init__(
        self,
        workspace: str,
        agent_dir: str,
        guild_binary: str = "guild",
        session_create_timeout: float = 180.0,
        response_timeout: float = 180.0,
        poll_interval: float = 5.0,
    ) -> None:
        """agent_dir is the local Guild agent checkout (contains guild.json)
        -- `guild agent chat` resolves the agent/workspace from it, there's
        no flag to name an unpublished draft agent by ID directly."""
        if not workspace or not agent_dir:
            raise GuildNotConfiguredError("workspace and agent_dir are required")
        self._workspace = workspace
        self._agent_dir = agent_dir
        self._guild_binary = guild_binary
        self._session_create_timeout = session_create_timeout
        self._response_timeout = response_timeout
        self._poll_interval = poll_interval

    def propose(
        self,
        run_id: str,
        base_commit: str,
        finding,
        source_files: Mapping[str, str],
        guidance_ids: tuple[str, ...] = (),
        attempt_number: int = 1,
    ) -> Candidate:
        if len(source_files) != 1:
            raise NotImplementedError("single-file repair only; multi-file source_files not supported yet")
        file_path, file_content = next(iter(source_files.items()))

        payload = {
            "filePath": file_path,
            "fileContent": file_content,
            "baseCommit": base_commit,
            "defectSummary": f"{finding.check_id}: {finding.detail or 'see adapter_origin for detection source'}",
            "defectLine": _extract_line(finding.detail) or 0,
            "guidance": list(guidance_ids),
        }

        session_id = self._create_session(payload)
        patch_text = self._await_diff(session_id)

        return Candidate(
            candidate_id=str(uuid.uuid4()),
            run_id=run_id,
            base_commit=base_commit,
            patch=patch_text,
            content_hash="",
            origin="guild-agent",
            linked_guidance_ids=guidance_ids,
            attempt_number=attempt_number,
        )

    def _create_session(self, payload: dict) -> str:
        proc = subprocess.Popen(
            [
                self._guild_binary,
                "agent",
                "chat",
                "--path",
                self._agent_dir,
                "--workspace",
                self._workspace,
                "--mode",
                "json",
                "--no-splash",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps(payload))
        proc.stdin.close()

        session_id: str | None = None
        deadline = time.monotonic() + self._session_create_timeout
        lines: list[str] = []
        try:
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                lines.append(line)
                match = _SESSION_ID_RE.search(line)
                if match:
                    session_id = match.group(1)
                    break
        finally:
            proc.terminate()

        if session_id is None:
            raise GuildSessionTimeoutError(
                f"no session ID observed within {self._session_create_timeout}s; output: {''.join(lines)[-2000:]}"
            )
        return session_id

    def _await_diff(self, session_id: str) -> str:
        deadline = time.monotonic() + self._response_timeout
        last_text = ""
        while time.monotonic() < deadline:
            try:
                proc = subprocess.run(
                    [self._guild_binary, "session", "events", session_id, "--events", "all"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                # A transient backend hiccup on this one poll, not a reason
                # to give up on the whole session -- retry until response_timeout.
                time.sleep(self._poll_interval)
                continue

            if proc.returncode == 0:
                try:
                    data = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    data = {"items": []}

                for item in reversed(data.get("items", [])):
                    if item.get("type") != "agent_notification_message":
                        continue
                    content = item.get("content")
                    text = content.get("data", "") if isinstance(content, dict) else ""
                    if not text:
                        continue
                    last_text = text
                    match = _DIFF_FENCE_RE.search(text)
                    if match:
                        return match.group(1).strip()

            time.sleep(self._poll_interval)

        if last_text:
            raise GuildResponseFormatError(
                f"session {session_id} produced a final message with no diff fence: {last_text[:2000]}"
            )
        raise GuildSessionTimeoutError(f"session {session_id} produced no response within {self._response_timeout}s")


def _extract_line(detail: str | None) -> int | None:
    if not detail:
        return None
    match = re.search(r":(\d+)(?:\D*)$", detail.strip())
    return int(match.group(1)) if match else None
