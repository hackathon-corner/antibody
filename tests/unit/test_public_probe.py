import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from adapters.public_probe import FIXTURE, probe

FX = json.loads(FIXTURE.read_text(encoding="utf-8"))
LEAK_ROW = {"id": 1, "name": "admin@juice-sh.op", "description": "0192023a7bbd73250516f069df18b500"}


def site(*, injection_rows=None, quote_status=200, ordinary=True, name="App", down=False):
    """A fake Juice Shop answering the probes' URLs."""
    def fetch(url):
        if down:
            raise OSError("connection refused")
        path = urllib.parse.urlparse(url)
        if path.path.endswith("application-configuration"):
            return 200, json.dumps({"config": {"application": {"name": name}}}).encode()
        q = urllib.parse.parse_qs(path.query, keep_blank_values=True)["q"][0]
        if q == FX["injection"]["payload"]:
            return 200, json.dumps({"status": "success", "data": injection_rows or []}).encode()
        if q == "O'Reilly":
            return (quote_status, b'{"status":"success","data":[]}' if quote_status == 200 else b"Internal error")
        expected = next(e["ids"] for e in FX["ordinaryQueries"] if e["q"] == q) if ordinary else []
        return 200, json.dumps({"status": "success", "data": [{"id": i} for i in expected]}).encode()
    return fetch


def run(fetch, mode="candidate", **kw):
    return probe("http://deploy.example", mode=mode, target_id="juice-shop", release_ref="akash:1", fetch=fetch, **kw)


def by_id(observations):
    return {o.probe_id: json.loads(o.redacted_result) for o in observations}


def test_repaired_site_passes_candidate_mode():
    ok, obs = run(site(), expect_name="App")
    assert ok
    ids = by_id(obs)
    assert ids["public.app-name"]["passed"] and ids["public.injection"]["credentialShapedRows"] == 0
    assert len([i for i in ids if i.startswith("public.search-ordinary.")]) == len(FX["ordinaryQueries"])
    assert all(o.release_ref == "akash:1" and o.target_id == "juice-shop" for o in obs)


def test_leaking_site_fails_candidate_mode_and_passes_baseline_mode():
    leaky = site(injection_rows=[LEAK_ROW], quote_status=500)
    ok, obs = run(leaky)
    assert not ok and not by_id(obs)["public.injection"]["passed"]
    ok, obs = run(leaky, mode="baseline")
    assert ok, "baseline mode expects the injection to reproduce; the quote 500 is recorded, not judged"
    assert by_id(obs)["public.search-quote"]["required"] is False


def test_search_that_returns_nothing_fails():
    ok, obs = run(site(ordinary=False))
    assert not ok and not by_id(obs)["public.search-ordinary.apple"]["passed"]


def test_wrong_application_name_fails():
    ok, _ = run(site(name="OWASP Juice Shop"), expect_name="OWASP Juice Shop (Antibody build spike)")
    assert not ok


def test_unreachable_endpoint_is_a_failed_observation():
    ok, obs = run(site(down=True))
    assert not ok and obs and all(o.status_code == 0 for o in obs)


def test_observations_never_carry_row_contents():
    _, obs = run(site(injection_rows=[LEAK_ROW]), mode="baseline")
    text = json.dumps([o.redacted_result for o in obs])
    assert "admin@juice-sh.op" not in text and LEAK_ROW["description"] not in text


@pytest.mark.parametrize("url,mode", [("file:///etc/passwd", "candidate"), ("http://x.example", "both")])
def test_bad_arguments_are_refused(url, mode):
    with pytest.raises(ValueError):
        probe(url, mode=mode, target_id="t", release_ref=None, fetch=site())
