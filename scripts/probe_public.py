"""External probe of a deployed target (B2, reused by B5). Prints Observation records as JSON.

    python scripts/probe_public.py --url https://<lease-host> [--expect-name "OWASP Juice Shop (Antibody build spike)"]
        [--release-ref <digest or lease id>]

Checks that the endpoint serves the application name we expect (proving our rebuilt image, not upstream's,
is answering) and that ordinary search returns the expected products from the B3 fixture.
Exit code: 0 all probes passed, 1 a probe failed or the endpoint was unreachable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from contracts import Observation  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "juice-shop" / "search-expectations.json"


def fetch(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("--target", default="juice-shop")
    parser.add_argument("--expect-name", help="application name the rebuilt image must report")
    parser.add_argument("--release-ref")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    apple = next(q["ids"] for q in fx["ordinaryQueries"] if q["q"] == "apple")

    observations, ok = [], True

    def observe(probe_id: str, path: str, judge) -> None:
        nonlocal ok
        url = base + path
        try:
            status, body = fetch(url)
            passed, summary = judge(status, body)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            status, body, passed, summary = 0, b"", False, {"error": str(exc)[:200]}
        ok = ok and passed
        observations.append(Observation(
            url=url, target_id=args.target, probe_id=probe_id, release_ref=args.release_ref,
            status_code=status, body_digest="sha256:" + hashlib.sha256(body).hexdigest(),
            observed_at=datetime.now(timezone.utc), redacted_result=json.dumps({"passed": passed, **summary}),
        ))

    def judge_name(status, body):
        name = json.loads(body)["config"]["application"]["name"] if status == 200 else None
        passed = status == 200 and (args.expect_name is None or name == args.expect_name)
        return passed, {"applicationName": name, "expected": args.expect_name}

    def judge_search(status, body):
        ids = [p["id"] for p in json.loads(body)["data"]] if status == 200 else None
        return status == 200 and ids == apple, {"q": "apple", "ids": ids, "expectedIds": apple}

    observe("public.app-name", "/rest/admin/application-configuration", judge_name)
    observe("public.search-ordinary", "/rest/products/search?q=apple", judge_search)

    print(json.dumps([{**asdict(o), "observed_at": o.observed_at.isoformat()} for o in observations], indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
