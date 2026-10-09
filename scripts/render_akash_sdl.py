"""Render infra/akash/juice-shop.sdl.template.yaml for one exact image digest (B2/B5).

    python scripts/render_akash_sdl.py --image ghcr.io/hackathon-corner/antibody-target@sha256:<64 hex>

Only digest references to the team's registry are accepted; tags such as `latest` are refused.
Output goes to the ignored runtime/akash/ directory. No credentials are written.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "infra" / "akash" / "juice-shop.sdl.template.yaml"
IMAGE_RE = re.compile(r"^ghcr\.io/hackathon-corner/antibody-target@sha256:[0-9a-f]{64}$")


def render(image: str) -> str:
    if not IMAGE_RE.match(image):
        raise ValueError("image must be ghcr.io/hackathon-corner/antibody-target@sha256:<64 hex>; tags are not accepted")
    return TEMPLATE.read_text(encoding="utf-8").replace("{{IMAGE}}", image)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        sdl = render(args.image)
    except ValueError as exc:
        sys.exit(str(exc))
    out = ROOT / "runtime" / "akash" / f"juice-shop-{args.image.rsplit(':', 1)[1][:12]}.sdl.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sdl, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
