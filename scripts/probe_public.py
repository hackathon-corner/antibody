"""External probe of a deployed target (B2, B5). Prints Observation records as JSON.

    python scripts/probe_public.py --url https://<lease-host> --mode baseline|candidate
        [--expect-name "OWASP Juice Shop (Antibody build spike)"] [--release-ref <digest or akash:dseq>]

Repeats the B3 fixture's public checks from outside the deployment: application name (if given),
ordinary search, the single-quote case and the selected injection. ``--mode`` is required: use
``baseline`` for an unrepaired build (injection must be reproduced, e.g. the B2 spike) and
``candidate`` for a repaired one (injection must not leak). See src/adapters/public_probe.py.
Exit code: 0 all required probes passed, 1 otherwise (including an unreachable endpoint).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from adapters.public_probe import observation_json, probe  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("--mode", required=True, choices=["baseline", "candidate"])
    parser.add_argument("--target", default="juice-shop")
    parser.add_argument("--expect-name", help="application name the rebuilt image must report")
    parser.add_argument("--release-ref")
    args = parser.parse_args()
    ok, observations = probe(args.url, mode=args.mode, target_id=args.target, release_ref=args.release_ref,
                             expect_name=args.expect_name)
    print(json.dumps([observation_json(o) for o in observations], indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
