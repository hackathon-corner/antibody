import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from adapters.senso import DEFAULT_CONTENT_IDS, SensoGuidanceAdapter, SensoRetrievalError


def fake_proc(returncode: int, stdout: str = "", stderr: str = ""):
    class _Proc:
        pass

    p = _Proc()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def test_retrieve_returns_tagged_passages() -> None:
    payload = {
        "answer": "Use parameterized queries via Sequelize replacements.",
        "results": [
            {
                "content_id": "2fc71565-db91-41a7-8c6d-f15b1abda7ed",
                "title": "Sequelize v6 Raw Queries",
                "text": "Use `replacements` for named parameters.",
            },
            {"content_id": "54036268-5be8-4cee-96e2-97e52ae95ab2", "title": "OWASP Cheat Sheet"},
        ],
    }
    with patch("subprocess.run", return_value=fake_proc(0, stdout=json.dumps(payload))):
        adapter = SensoGuidanceAdapter()
        passages = adapter.retrieve("how do I parameterize a sequelize query")

    assert passages[0] == "[synthesized] Use parameterized queries via Sequelize replacements."
    assert any(p.startswith("[2fc71565-db91-41a7-8c6d-f15b1abda7ed]") for p in passages)
    assert any("Use `replacements` for named parameters." in p for p in passages)
    # Result with no text field falls back to title only, not a crash.
    assert any(p == "[54036268-5be8-4cee-96e2-97e52ae95ab2] OWASP Cheat Sheet" for p in passages)


def test_scopes_search_to_pinned_content_ids() -> None:
    captured_cmd = {}

    def fake_run(cmd, **kwargs):
        captured_cmd["cmd"] = cmd
        return fake_proc(0, stdout=json.dumps({"answer": "x", "results": []}))

    with patch("subprocess.run", side_effect=fake_run):
        SensoGuidanceAdapter().retrieve("query")

    cmd = captured_cmd["cmd"]
    assert "--require-scoped-ids" in cmd
    idx = cmd.index("--content-ids")
    passed_ids = cmd[idx + 1 : idx + 1 + len(DEFAULT_CONTENT_IDS)]
    assert tuple(passed_ids) == DEFAULT_CONTENT_IDS


def test_nonzero_exit_raises() -> None:
    with patch("subprocess.run", return_value=fake_proc(1, stderr="not authenticated")):
        with pytest.raises(SensoRetrievalError, match="not authenticated"):
            SensoGuidanceAdapter().retrieve("query")


def test_invalid_json_raises() -> None:
    with patch("subprocess.run", return_value=fake_proc(0, stdout="not json")):
        with pytest.raises(SensoRetrievalError, match="valid JSON"):
            SensoGuidanceAdapter().retrieve("query")


def test_empty_results_and_no_answer_raises() -> None:
    with patch("subprocess.run", return_value=fake_proc(0, stdout=json.dumps({"results": []}))):
        with pytest.raises(SensoRetrievalError, match="no results"):
            SensoGuidanceAdapter().retrieve("query")


def test_custom_content_ids_override_default() -> None:
    captured_cmd = {}

    def fake_run(cmd, **kwargs):
        captured_cmd["cmd"] = cmd
        return fake_proc(0, stdout=json.dumps({"answer": "x", "results": []}))

    with patch("subprocess.run", side_effect=fake_run):
        SensoGuidanceAdapter(content_ids=("custom-id-1",)).retrieve("query")

    cmd = captured_cmd["cmd"]
    idx = cmd.index("--content-ids")
    assert cmd[idx + 1] == "custom-id-1"
