"""Render infra/akash/evidence-api.sdl.template.yaml for one image digest (C3).

    python scripts/render_evidence_sdl.py --image ghcr.io/hackathon-corner/antibody-evidence-api@sha256:<64 hex>

Reads CLICKHOUSE_HOST/PORT/DATABASE and the read-only CLICKHOUSE_READER_USER/PASSWORD from the
ignored .env. Refuses the read-write app user, because the Akash provider can read the SDL's env.
Writes to the ignored runtime/akash/ directory and prints only the path.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "infra" / "akash" / "evidence-api.sdl.template.yaml"
IMAGE_RE = re.compile(r"^ghcr\.io/hackathon-corner/antibody-evidence-api@sha256:[0-9a-f]{64}$")
KEYS = ("CLICKHOUSE_HOST", "CLICKHOUSE_PORT", "CLICKHOUSE_DATABASE", "CLICKHOUSE_READER_USER", "CLICKHOUSE_READER_PASSWORD")


def load_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def render(image: str, env: dict[str, str]) -> str:
    if not IMAGE_RE.match(image):
        raise ValueError("image must be ghcr.io/hackathon-corner/antibody-evidence-api@sha256:<64 hex>; tags are not accepted")
    missing = [k for k in KEYS if not env.get(k)]
    if missing:
        raise ValueError(f"missing in .env: {', '.join(missing)}")
    if env["CLICKHOUSE_READER_USER"] in (env.get("CLICKHOUSE_USER"), "default"):
        raise ValueError("CLICKHOUSE_READER_USER must be a separate read-only user, not the app or admin user")
    for key, value in env.items():
        if '"' in value or "\n" in value:
            raise ValueError(f"{key} contains a character that would break the SDL")
    sdl = TEMPLATE.read_text(encoding="utf-8").replace("{{IMAGE}}", image)
    for key in KEYS:
        sdl = sdl.replace("{{" + key + "}}", env[key])
    return sdl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", required=True)
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    args = parser.parse_args()
    try:
        sdl = render(args.image, load_env(Path(args.env_file)))
    except (ValueError, FileNotFoundError) as exc:
        sys.exit(str(exc))
    out = ROOT / "runtime" / "akash" / f"evidence-api-{args.image.rsplit(':', 1)[1][:12]}.sdl.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sdl, encoding="utf-8")
    out.chmod(0o600)
    print(out)


if __name__ == "__main__":
    main()
