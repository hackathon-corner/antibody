import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from adapters.guild import (
    GuildNotConfiguredError,
    GuildPatchAdapter,
    GuildResponseFormatError,
    GuildSessionTimeoutError,
    _extract_line,
)
from contracts import CheckResult, CheckStatus
from datetime import datetime, timezone

SOURCE = {"routes/search.ts": "vulnerable content"}


def make_finding() -> CheckResult:
    return CheckResult(
        check_id="javascript.sequelize.security.audit.sequelize-injection-express.express-sequelize-injection",
        candidate_hash="",
        status=CheckStatus.FAIL,
        observed_at=datetime.now(timezone.utc),
        artifact_ref=None,
        adapter_origin="semgrep",
        detail="1 match(es) at routes/search.ts:23",
    )


def test_requires_workspace_and_agent() -> None:
    with pytest.raises(GuildNotConfiguredError):
        GuildPatchAdapter(workspace="", agent_dir="")


def fake_create_proc(session_line: str):
    proc = MagicMock()
    proc.stdin = MagicMock()
    lines = iter([session_line, ""])
    proc.stdout.readline.side_effect = lambda: next(lines, "")
    proc.poll.return_value = 0
    return proc


def fake_events_proc(returncode: int, items: list[dict]):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = json.dumps({"items": items})
    return proc


def test_propose_end_to_end_extracts_diff() -> None:
    diff_text = "--- a/routes/search.ts\n+++ b/routes/search.ts\n@@ -1 +1 @@\n-old\n+new\n"
    message_text = f"```diff\n{diff_text}```"

    with patch("subprocess.Popen", return_value=fake_create_proc("✓ Session: sess-123\n")), patch(
        "subprocess.run",
        return_value=fake_events_proc(
            0,
            [{"type": "agent_notification_message", "content": {"data": message_text}}],
        ),
    ):
        adapter = GuildPatchAdapter(workspace="g3ram~antibody-dev", agent_dir="/tmp/fake-agent-dir")
        candidate = adapter.propose(
            run_id="r1",
            base_commit="abc123",
            finding=make_finding(),
            source_files=SOURCE,
        )

    assert candidate.patch == diff_text.strip()
    assert candidate.origin == "guild-agent"
    assert candidate.base_commit == "abc123"
    assert candidate.content_hash == ""


def test_session_id_not_observed_raises() -> None:
    with patch("subprocess.Popen", return_value=fake_create_proc("no session line here\n")):
        adapter = GuildPatchAdapter(
            workspace="g3ram~antibody-dev",
            agent_dir="/tmp/fake-agent-dir",
            session_create_timeout=0.01,
        )
        with pytest.raises(GuildSessionTimeoutError):
            adapter.propose(run_id="r1", base_commit="abc123", finding=make_finding(), source_files=SOURCE)


def test_final_message_without_diff_fence_raises() -> None:
    with patch("subprocess.Popen", return_value=fake_create_proc("✓ Session: sess-123\n")), patch(
        "subprocess.run",
        return_value=fake_events_proc(
            0,
            [{"type": "agent_notification_message", "content": {"data": "I refuse to produce a diff."}}],
        ),
    ):
        adapter = GuildPatchAdapter(
            workspace="g3ram~antibody-dev",
            agent_dir="/tmp/fake-agent-dir",
            response_timeout=0.01,
            poll_interval=0.001,
        )
        with pytest.raises(GuildResponseFormatError):
            adapter.propose(run_id="r1", base_commit="abc123", finding=make_finding(), source_files=SOURCE)


def test_transient_poll_timeout_is_retried_not_fatal() -> None:
    # Reproduces a real failure observed live: subprocess.run's own timeout
    # expiring on one poll must not crash propose() -- it should retry.
    import subprocess as sp

    diff_text = "--- a/routes/search.ts\n+++ b/routes/search.ts\n@@ -1 +1 @@\n-old\n+new\n"
    message_text = f"```diff\n{diff_text}```"
    responses = iter(
        [
            sp.TimeoutExpired(cmd="guild", timeout=30),
            fake_events_proc(
                0, [{"type": "agent_notification_message", "content": {"data": message_text}}]
            ),
        ]
    )

    def fake_run(*args, **kwargs):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("subprocess.Popen", return_value=fake_create_proc("✓ Session: sess-123\n")), patch(
        "subprocess.run", side_effect=fake_run
    ):
        adapter = GuildPatchAdapter(
            workspace="g3ram~antibody-dev", agent_dir="/tmp/fake-agent-dir", poll_interval=0.001
        )
        candidate = adapter.propose(run_id="r1", base_commit="abc123", finding=make_finding(), source_files=SOURCE)

    assert candidate.patch == diff_text.strip()


def test_no_response_at_all_times_out() -> None:
    with patch("subprocess.Popen", return_value=fake_create_proc("✓ Session: sess-123\n")), patch(
        "subprocess.run", return_value=fake_events_proc(0, [])
    ):
        adapter = GuildPatchAdapter(
            workspace="g3ram~antibody-dev",
            agent_dir="/tmp/fake-agent-dir",
            response_timeout=0.01,
            poll_interval=0.001,
        )
        with pytest.raises(GuildSessionTimeoutError):
            adapter.propose(run_id="r1", base_commit="abc123", finding=make_finding(), source_files=SOURCE)


def test_multi_file_source_not_supported_yet() -> None:
    adapter = GuildPatchAdapter(workspace="g3ram~antibody-dev", agent_dir="/tmp/fake-agent-dir")
    with pytest.raises(NotImplementedError):
        adapter.propose(
            run_id="r1",
            base_commit="abc123",
            finding=make_finding(),
            source_files={"a.ts": "x", "b.ts": "y"},
        )


@pytest.mark.parametrize(
    "detail,expected",
    [
        ("1 match(es) at routes/search.ts:23", 23),
        (None, None),
        ("no line info here", None),
    ],
)
def test_extract_line(detail, expected) -> None:
    assert _extract_line(detail) == expected
