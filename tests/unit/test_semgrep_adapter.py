import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from adapters.semgrep import SemgrepAdapter, SemgrepScanError

RULE_ID = "javascript.sequelize.security.audit.sequelize-injection-express.express-sequelize-injection"


def fake_proc(returncode: int, payload: dict):
    class _Proc:
        pass

    p = _Proc()
    p.returncode = returncode
    p.stdout = json.dumps(payload)
    p.stderr = ""
    return p


def test_matches_check_id_prefixed_by_local_rule_file_path() -> None:
    # Mirrors what C observed: scanning from a locally fetched rule file
    # prefixes check_id with the file's directory path.
    payload = {
        "errors": [],
        "results": [
            {
                "check_id": f"private.tmp.abc123.{RULE_ID}",
                "path": "routes/search.ts",
                "start": {"line": 23},
            }
        ],
    }
    with patch("subprocess.run", return_value=fake_proc(1, payload)):
        adapter = SemgrepAdapter(config_path="/tmp/fetched-rule.yml")
        results = adapter.scan("routes/search.ts", (RULE_ID,))

    assert len(results) == 1
    assert results[0].status.value == "fail"
    assert "routes/search.ts:23" in results[0].detail


def test_matches_bare_registry_rule_id() -> None:
    payload = {
        "errors": [],
        "results": [{"check_id": RULE_ID, "path": "routes/search.ts", "start": {"line": 23}}],
    }
    with patch("subprocess.run", return_value=fake_proc(1, payload)):
        adapter = SemgrepAdapter(config_path="/tmp/fetched-rule.yml")
        results = adapter.scan("routes/search.ts", (RULE_ID,))

    assert results[0].status.value == "fail"


def test_no_match_is_pass() -> None:
    payload = {"errors": [], "results": []}
    with patch("subprocess.run", return_value=fake_proc(0, payload)):
        adapter = SemgrepAdapter(config_path="/tmp/fetched-rule.yml")
        results = adapter.scan("routes/search.ts", (RULE_ID,))

    assert results[0].status.value == "pass"


def test_does_not_cross_match_a_different_rule_id_suffix() -> None:
    # A check_id ending in a *different* rule shouldn't satisfy this one,
    # even though endswith is used instead of exact match.
    payload = {
        "errors": [],
        "results": [
            {"check_id": "some.other.totally-unrelated-rule", "path": "x.ts", "start": {"line": 1}}
        ],
    }
    with patch("subprocess.run", return_value=fake_proc(1, payload)):
        adapter = SemgrepAdapter(config_path="/tmp/fetched-rule.yml")
        results = adapter.scan("routes/search.ts", (RULE_ID,))

    assert results[0].status.value == "pass"


def test_scan_errors_raise() -> None:
    payload = {"errors": [{"message": "parse error"}], "results": []}
    with patch("subprocess.run", return_value=fake_proc(0, payload)):
        adapter = SemgrepAdapter(config_path="/tmp/fetched-rule.yml")
        try:
            adapter.scan("routes/search.ts", (RULE_ID,))
            assert False, "expected SemgrepScanError"
        except SemgrepScanError:
            pass


def test_unexpected_exit_code_raises() -> None:
    with patch("subprocess.run", return_value=fake_proc(2, {"errors": [], "results": []})):
        adapter = SemgrepAdapter(config_path="/tmp/fetched-rule.yml")
        try:
            adapter.scan("routes/search.ts", (RULE_ID,))
            assert False, "expected SemgrepScanError"
        except SemgrepScanError:
            pass
