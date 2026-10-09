"""Pinned target operations (B1): export source, build, run, smoke-check.

Every pin comes from config/targets/<target>.json. Nothing here accepts an
arbitrary repository, commit, or base image from the command line.

    python scripts/target.py source --out runtime/source
    python scripts/target.py build [--patch candidate.patch]
    python scripts/target.py run --image sha256:... [--port 3000]
    python scripts/target.py smoke --url http://localhost:3000
    python scripts/target.py stop
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "baseline"


def load_target(target_id: str) -> dict:
    return json.loads((ROOT / "config" / "targets" / f"{target_id}.json").read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def cmd_source(target: dict, args: argparse.Namespace) -> None:
    """Export only the allowed repair paths at the pinned commit.

    Avoids a full checkout (upstream has paths too long for default Windows git).
    """
    src = target["source"]
    out = Path(args.out).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        run(["git", "init", "-q", tmp])
        run(["git", "-C", tmp, "fetch", "-q", "--depth", "1", src["repo"], src["commit"]])
        head = run(["git", "-C", tmp, "rev-parse", "FETCH_HEAD"], capture_output=True).stdout.strip()
        if head != src["commit"]:
            sys.exit(f"fetched {head}, expected pinned {src['commit']}")
        for rel in target["allowed_paths"]:
            data = subprocess.run(
                ["git", "-C", tmp, "show", f"FETCH_HEAD:{rel}"], check=True, capture_output=True
            ).stdout
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            print(f"{rel}\tsha256:{sha256_bytes(data)}")
    print(f"exported commit {src['commit']} to {out}")


def cmd_build(target: dict, args: argparse.Namespace) -> None:
    patch = Path(args.patch).read_bytes() if args.patch else b""
    # Same hash A's CandidateValidator computes over the patch text.
    candidate_hash = sha256_bytes(patch) if patch else BASELINE
    dockerfile = ROOT / target["dockerfile"]
    images = target["base_images"]
    tag = f"antibody/{target['target_id']}:{candidate_hash[:12]}"

    with tempfile.TemporaryDirectory() as ctx:
        (Path(ctx) / "candidate.patch").write_bytes(patch)
        run([
            "docker", "build",
            "-f", str(dockerfile),
            "--build-arg", f"GIT_IMAGE={images['git']}",
            "--build-arg", f"BUILD_IMAGE={images['build']}",
            "--build-arg", f"RUNTIME_IMAGE={images['runtime']}",
            "--build-arg", f"SOURCE_REPO={target['source']['repo']}",
            "--build-arg", f"SOURCE_COMMIT={target['source']['commit']}",
            "--build-arg", f"CANDIDATE_HASH={candidate_hash}",
            "-t", tag,
            ctx,
        ])

    image_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", tag], capture_output=True).stdout.strip()
    record = {
        "target_id": target["target_id"],
        "source_commit": target["source"]["commit"],
        "candidate_hash": candidate_hash,
        "image_tag": tag,
        "image_id": image_id,
        "registry_digest": None,
        "dockerfile_sha256": sha256_bytes(dockerfile.read_bytes()),
        "base_images": images,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    out_dir = ROOT / "runtime" / "builds"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{candidate_hash[:12]}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))


def container_name(target: dict) -> str:
    return f"antibody-{target['target_id']}"


def cmd_run(target: dict, args: argparse.Namespace) -> None:
    name = container_name(target)
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    run([
        "docker", "run", "-d", "--name", name,
        "-p", f"127.0.0.1:{args.port}:{target['container_port']}",
        "--memory", "2g", "--cpus", "2",
        args.image,
    ])
    print(f"started {name} from {args.image} on http://127.0.0.1:{args.port}")


def cmd_stop(target: dict, args: argparse.Namespace) -> None:
    run(["docker", "rm", "-f", container_name(target)])


def cmd_smoke(target: dict, args: argparse.Namespace) -> None:
    """Liveness sanity check only; the real before/after checks are B3's suite in tests/e2e."""
    url = f"{args.url.rstrip('/')}{target['search_path']}?q=apple"
    deadline = time.monotonic() + args.wait
    while True:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                body = json.loads(resp.read())
                break
        except (urllib.error.URLError, ConnectionError) as exc:
            if time.monotonic() > deadline:
                sys.exit(f"search not reachable at {url}: {exc}")
            time.sleep(3)
    products = body.get("data") if isinstance(body, dict) else None
    if not products:
        sys.exit(f"search reachable but returned no products: {str(body)[:200]}")
    print(f"ok: {len(products)} product(s) for q=apple, ids={[p.get('id') for p in products]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="juice-shop")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("source", help="export allowed paths at the pinned commit")
    p.add_argument("--out", required=True)
    p = sub.add_parser("build", help="build the pinned target, optionally with a candidate patch")
    p.add_argument("--patch", help="unified diff against the pinned commit; omit for baseline")
    p = sub.add_parser("run", help="run a built image on localhost")
    p.add_argument("--image", required=True)
    p.add_argument("--port", type=int, default=3000)
    sub.add_parser("stop", help="remove the running target container")
    p = sub.add_parser("smoke", help="check that product search answers")
    p.add_argument("--url", default="http://127.0.0.1:3000")
    p.add_argument("--wait", type=int, default=120, help="seconds to wait for startup")

    args = parser.parse_args()
    if shutil.which("git") is None or (args.command in {"build", "run", "stop"} and shutil.which("docker") is None):
        sys.exit("required tool not found on PATH (git, and docker for build/run/stop)")
    commands = {"source": cmd_source, "build": cmd_build, "run": cmd_run, "stop": cmd_stop, "smoke": cmd_smoke}
    commands[args.command](load_target(args.target), args)


if __name__ == "__main__":
    main()
