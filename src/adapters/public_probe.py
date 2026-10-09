"""B5: external probes of a deployed target. Each probe emits one ``Observation``.

The probes repeat the B3 fixture's public checks from outside the deployment:
- ``public.app-name``: the endpoint reports the application name we expect (optional; proves
  our rebuilt image, not upstream's, is answering);
- ``public.search-ordinary.<q>``: each ordinary query returns exactly the fixture's product IDs;
- ``public.search-quote``: a single quote is handled (candidate mode; the baseline returns 500);
- ``public.injection``: the fixture's union payload.

``mode`` says what the injection result must be: ``candidate`` requires HTTP 200 JSON with no
credential-shaped rows; ``baseline`` requires the injection to be reproduced (for probing an
unrepaired build such as the B2 spike). In baseline mode the quote probe is recorded, not judged.

Observations carry statuses, counts, IDs of fixture products and body digests, never row
contents. An unreachable endpoint is a failed observation with status 0, not a skipped one.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from contracts import Observation

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "juice-shop" / "search-expectations.json"

Fetch = Callable[[str], tuple[int, bytes]]


def http_get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _json(body: bytes):
    try:
        return json.loads(body)
    except ValueError:
        return None


def _rows(body: bytes) -> list | None:
    doc = _json(body)
    data = doc.get("data") if isinstance(doc, dict) else None
    return data if isinstance(data, list) else None


def _credential_shaped(rows: list) -> int:
    return sum(1 for r in rows if "@" in str(r.get("name", "")) or
               (len(str(r.get("description", ""))) == 32 and all(c in "0123456789abcdef" for c in str(r.get("description")))))


def probe(base_url: str, *, mode: str, target_id: str, release_ref: str | None,
          expect_name: str | None = None, fetch: Fetch = http_get) -> tuple[bool, tuple[Observation, ...]]:
    if mode not in ("baseline", "candidate"):
        raise ValueError("mode must be 'baseline' or 'candidate'")
    if urllib.parse.urlparse(base_url).scheme not in ("http", "https"):
        raise ValueError("base_url must be http(s)")
    base = base_url.rstrip("/")
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    observations: list[Observation] = []
    ok = True

    def observe(probe_id: str, path: str, judge, required: bool = True) -> None:
        nonlocal ok
        url = base + path
        try:
            status, body = fetch(url)
        except (urllib.error.URLError, OSError) as exc:
            status, body, passed, summary = 0, b"", False, {"error": str(exc)[:200]}
        else:
            passed, summary = judge(status, body)
        if required:
            ok = ok and passed
        observations.append(Observation(
            url=url, target_id=target_id, probe_id=probe_id, release_ref=release_ref, status_code=status,
            body_digest="sha256:" + hashlib.sha256(body).hexdigest(), observed_at=datetime.now(timezone.utc),
            redacted_result=json.dumps({"passed": passed, "required": required, "mode": mode, **summary}),
        ))

    def search(q: str) -> str:
        return "/rest/products/search?q=" + urllib.parse.quote(q, safe="")

    if expect_name is not None:
        def judge_name(status, body):
            doc = _json(body) if status == 200 else None
            name = (((doc or {}).get("config") or {}).get("application") or {}).get("name") if isinstance(doc, dict) else None
            return status == 200 and name == expect_name, {"applicationName": name, "expected": expect_name}
        observe("public.app-name", "/rest/admin/application-configuration", judge_name)

    for entry in fx["ordinaryQueries"]:
        def judge_search(status, body, expected=entry["ids"], q=entry["q"]):
            rows = _rows(body) if status == 200 else None
            ids = [r.get("id") for r in rows] if rows is not None else None
            return ids == expected, {"q": q, "count": None if ids is None else len(ids), "idsMatch": ids == expected}
        observe(f"public.search-ordinary.{entry['q'] or 'empty'}", search(entry["q"]), judge_search)

    quote = next(e for e in fx["edgeCases"] if e["id"] == "quote")

    def judge_quote(status, body):
        rows = _rows(body) if status == 200 else None
        ids = [r.get("id") for r in rows] if rows is not None else None
        exp = quote["candidate"]
        return status == exp["status"] and ids == exp["ids"], {"q": "single quote", "count": None if ids is None else len(ids)}
    observe("public.search-quote", search(quote["q"]), judge_quote, required=(mode == "candidate"))

    def judge_injection(status, body):
        rows = _rows(body) if status == 200 else None
        shaped = _credential_shaped(rows) if rows is not None else 0
        leaked = shaped > 0
        if mode == "baseline":
            return leaked, {"expectation": "reproduce", "rowCount": None if rows is None else len(rows),
                            "credentialShapedRows": shaped}
        return status == 200 and rows is not None and not leaked, {
            "expectation": "no-leak, HTTP 200 JSON", "rowCount": None if rows is None else len(rows),
            "credentialShapedRows": shaped}
    observe("public.injection", search(fx["injection"]["payload"]), judge_injection)

    return ok, tuple(observations)


def observation_json(o: Observation) -> dict:
    return {**asdict(o), "observed_at": o.observed_at.isoformat()}


__all__ = ["http_get", "observation_json", "probe"]
