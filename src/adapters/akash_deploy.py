"""B5: fixed Akash deployment connector for verified candidates.

``deploy(DeployRequest)`` takes only a candidate hash and the image digest the check worker
verified. It never takes a host, URL, command or tag. Before anything leaves this machine it
re-reads the worker's verification record and refuses unless that exact candidate and image
passed the current suite.

Then it:
1. pushes that local image to the fixed registry repo as ``cand-<hash12>`` and deploys it by
   the registry digest the push reports (never by tag);
2. renders the fixed SDL template for that digest. The package is public; if it is ever made
   private again, set ``GHCR_PULL_USER``/``GHCR_PULL_TOKEN`` (read:packages only) and they are
   added to the SDL;
3. creates the deployment through the Akash Console API (``AKASH_API_KEY``), leases the
   cheapest bid, and waits for the service to report a URI.

Deployments are serialized: one coordinator row in a local SQLite store, and every step is
recorded there before the next one starts. A crash or timeout leaves the attempt non-terminal;
``reconcile()`` asks Akash what actually exists instead of deploying again.

Outcomes are reported as they are. ``ACCEPTED`` means Akash has an active lease with a service
URI for this image; it is not proof the image is serving. External probes decide that.
Anything that may have created a deployment but could not be confirmed is ``UNKNOWN``.
Credentials are never written to the store, the rendered SDL on disk, or results.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from contracts import DeployRequest, DeployResult, DeployStatus, Observation

from .check_worker import ROOT, suite_hash
from .public_probe import Fetch, http_get, probe

CONSOLE_API = "https://console-api.akash.network"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PUSH_DIGEST = re.compile(r"digest: (sha256:[0-9a-f]{64})")
_TERMINAL = ("accepted", "failed", "closed")


class AkashApiError(RuntimeError):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(f"Akash Console API {status or 'unreachable'}: {message}")
        self.status = status

    @property
    def maybe_applied(self) -> bool:
        """True when the request may have taken effect (no answer, or a server-side error)."""
        return self.status is None or self.status >= 500


class AkashApi(Protocol):
    def create_deployment(self, sdl: str) -> str: ...
    def bids(self, dseq: str) -> list[dict]: ...
    def create_lease(self, dseq: str, gseq: int, oseq: int, provider: str) -> dict: ...
    def deployment(self, dseq: str) -> dict: ...
    def close(self, dseq: str) -> None: ...


class Registry(Protocol):
    def push(self, image_id: str, tag: str) -> str:
        """Push the local image under ``tag`` and return the registry ``repo@sha256:...`` reference."""
        ...


class AkashConsoleApi:
    """Thin client for the Akash Console managed-wallet API (x-api-key auth)."""

    def __init__(self, api_key: str | None = None, base_url: str = CONSOLE_API, timeout: float = 60) -> None:
        key = api_key or os.environ.get("AKASH_API_KEY")
        if not key:
            raise RuntimeError("AKASH_API_KEY is not set")
        self._key, self._base, self._timeout = key, base_url.rstrip("/"), timeout

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(self._base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"x-api-key": self._key, "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raise AkashApiError(exc.code, exc.read().decode("utf-8", "replace")[:300]) from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise AkashApiError(None, str(exc)[:300]) from exc

    def create_deployment(self, sdl: str) -> str:
        return str(self._call("POST", "/v1/deployments", {"data": {"sdl": sdl}})["data"]["dseq"])

    def bids(self, dseq: str) -> list[dict]:
        return self._call("GET", f"/v1/bids?dseq={dseq}").get("data", [])

    def create_lease(self, dseq: str, gseq: int, oseq: int, provider: str) -> dict:
        lease = {"dseq": dseq, "gseq": gseq, "oseq": oseq, "provider": provider}
        return self._call("POST", "/v1/leases", {"leases": [lease]}).get("data", {})

    def deployment(self, dseq: str) -> dict:
        return self._call("GET", f"/v1/deployments/{dseq}").get("data", {})

    def close(self, dseq: str) -> None:
        self._call("DELETE", f"/v1/deployments/{dseq}")


class DockerRegistry:
    """Pushes with the operator's existing ``docker login ghcr.io`` (write:packages). Host only."""

    def __init__(self, repo: str, docker: str = "docker", timeout: float = 900) -> None:
        self._repo, self._docker, self._timeout = repo, docker, timeout

    def push(self, image_id: str, tag: str) -> str:
        ref = f"{self._repo}:{tag}"
        for cmd in ([self._docker, "tag", image_id, ref], [self._docker, "push", ref]):
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            if out.returncode != 0:
                raise RuntimeError(f"{' '.join(cmd[1:2])} failed: {out.stderr.strip()[-300:]}")
        match = _PUSH_DIGEST.search(out.stdout)
        if not match:
            raise RuntimeError("push reported no digest")
        return f"{self._repo}@{match.group(1)}"


class _Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, candidate_hash TEXT NOT NULL,
                image_id TEXT NOT NULL, registry_ref TEXT, dseq TEXT, provider TEXT, uri TEXT,
                state TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS coordinator (
                id INTEGER PRIMARY KEY CHECK (id = 1), attempt_id TEXT NOT NULL);
        """)

    def begin(self, request: DeployRequest) -> tuple[str | None, str | None]:
        """Claim the coordinator for a new attempt. Returns (attempt_id, None) or (None, holder)."""
        attempt_id = f"akash-{uuid.uuid4().hex[:16]}"
        now = _now()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute("SELECT attempt_id FROM coordinator").fetchone()
            if row:
                self._db.execute("ROLLBACK")
                return None, row[0]
            self._db.execute("INSERT INTO coordinator VALUES (1, ?)", (attempt_id,))
            self._db.execute("INSERT INTO attempts VALUES (?,?,?,?,NULL,NULL,NULL,NULL,'started',NULL,?,?)",
                             (attempt_id, request.run_id, request.candidate_hash, request.built_image_digest, now, now))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return attempt_id, None

    def update(self, attempt_id: str, **fields) -> None:
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._db.execute(f"UPDATE attempts SET {cols} WHERE attempt_id = ?", (*fields.values(), attempt_id))

    def release(self, attempt_id: str) -> None:
        self._db.execute("DELETE FROM coordinator WHERE attempt_id = ?", (attempt_id,))

    def get(self, attempt_id: str) -> dict | None:
        cur = self._db.execute("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,))
        row = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], row)) if row else None

    def open_attempts(self) -> list[dict]:
        cur = self._db.execute(
            f"SELECT * FROM attempts WHERE state NOT IN ({','.join('?' * len(_TERMINAL))}) ORDER BY created_at",
            _TERMINAL)
        return [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]

    def holder(self) -> str | None:
        row = self._db.execute("SELECT attempt_id FROM coordinator").fetchone()
        return row[0] if row else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AkashDeployConnector:
    def __init__(self, target: dict, *, api: AkashApi | None = None, registry: Registry | None = None,
                 runtime_dir: Path | None = None, env: dict | None = None,
                 bid_timeout: float = 180, ready_timeout: float = 600, poll_interval: float = 10,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        deploy = target["deploy"]
        self._target_id = target["target_id"]
        self._repo = deploy["registry_repo"]
        self._service = deploy["service"]
        self._template = (ROOT / deploy["sdl_template"]).read_text(encoding="utf-8")
        self._runtime = runtime_dir or ROOT / "runtime"
        self._env = os.environ if env is None else env
        self._api = api
        self._registry = registry or DockerRegistry(self._repo)
        self._store = _Store(self._runtime / "deploy" / "akash.sqlite")
        self._bid_timeout, self._ready_timeout, self._poll = bid_timeout, ready_timeout, poll_interval
        self._sleep, self._clock = sleep, clock

    # ---- runner entry points ---------------------------------------------------------------

    def deploy(self, request: DeployRequest) -> DeployResult:
        problem = self._verify(request)
        if problem:
            return self._result(f"rejected-{uuid.uuid4().hex[:8]}", request.built_image_digest, None,
                                DeployStatus.FAILED, problem)
        attempt_id, holder = self._store.begin(request)
        if attempt_id is None:
            return self._result(f"refused-{uuid.uuid4().hex[:8]}", request.built_image_digest, None,
                                DeployStatus.UNKNOWN, f"deployment {holder} is still unresolved; reconcile first")
        return self._attempt(attempt_id, request)  # an UNKNOWN outcome keeps the coordinator until reconciled

    def reconcile(self) -> list[DeployResult]:
        """Resolve non-terminal attempts against Akash's actual state. Never redeploys."""
        results = []
        for a in self._store.open_attempts():
            if not a["dseq"]:
                if a["state"] == "creating":
                    results.append(self._finish(a["attempt_id"], DeployStatus.UNKNOWN,
                                                "create request sent but no dseq recorded; check the Akash Console"))
                    continue
                results.append(self._finish(a["attempt_id"], DeployStatus.FAILED,
                                            f"interrupted before any Akash deployment ({a['state']})"))
                continue
            try:
                dep = self._akash().deployment(a["dseq"])
            except AkashApiError as exc:
                results.append(self._finish(a["attempt_id"], DeployStatus.UNKNOWN, str(exc)))
                continue
            state, uri, provider = self._lease_state(dep)
            if state == "closed":
                results.append(self._finish(a["attempt_id"], DeployStatus.FAILED, "deployment is closed on Akash",
                                            state="closed"))
            elif uri:
                self._store.update(a["attempt_id"], uri=uri, provider=provider)
                results.append(self._finish(a["attempt_id"], DeployStatus.ACCEPTED, None))
            else:
                results.append(self._finish(a["attempt_id"], DeployStatus.UNKNOWN,
                                            f"deployment {a['dseq']} has no ready service URI yet"))
        return results

    def endpoint(self, attempt_id: str) -> str | None:
        """Public URL Akash reported for an accepted attempt, for the external probes."""
        a = self._store.get(attempt_id)
        if not a or a["state"] != "accepted" or not a["uri"]:
            return None
        return a["uri"] if a["uri"].startswith("http") else f"http://{a['uri']}"

    def observe(self, attempt_id: str, *, mode: str = "candidate", expect_name: str | None = None,
                fetch: Fetch = http_get) -> tuple[bool, tuple[Observation, ...]]:
        """Run the external probes against an accepted attempt's public URL (B5).

        The verdict goes to HostRunner.complete(); a deploy is not verified until this passes.
        """
        url = self.endpoint(attempt_id)
        if url is None:
            raise RuntimeError(f"attempt {attempt_id} has no accepted public endpoint to probe")
        a = self._store.get(attempt_id)
        return probe(url, mode=mode, target_id=self._target_id, release_ref=f"akash:{a['dseq']}",
                     expect_name=expect_name, fetch=fetch)

    def close(self, attempt_id: str) -> None:
        """Close the attempt's Akash deployment (end of event, or recovery). Raises on failure."""
        a = self._store.get(attempt_id)
        if not a or not a["dseq"]:
            raise RuntimeError(f"attempt {attempt_id} has no Akash deployment")
        self._akash().close(a["dseq"])
        self._store.update(attempt_id, state="closed")
        self._store.release(attempt_id)

    # ---- internals -------------------------------------------------------------------------

    def _verify(self, request: DeployRequest) -> str | None:
        h, image = request.candidate_hash, request.built_image_digest
        if not _HASH.match(h or ""):
            return "candidate hash must be 64 lowercase hex characters"
        if not _DIGEST.match(image or ""):
            return "image must be an exact sha256 digest; tags and references are not accepted"
        path = self._runtime / "checks" / h[:12] / "result.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return f"candidate {h[:12]} has no readable verification record"
        if record.get("candidate_hash") != h:
            return f"verification record belongs to {record.get('candidate_hash')}, not {h}"
        if not record.get("passed"):
            return f"candidate {h[:12]} did not pass the required checks"
        if record.get("image_id") != image:
            return f"image {image} is not the image the checks ran against ({record.get('image_id')})"
        if record.get("suite_hash") != suite_hash():
            return "check suite changed since this candidate was verified; re-run checks"
        return None

    def _attempt(self, attempt_id: str, request: DeployRequest) -> DeployResult:
        st = self._store
        try:
            api = self._akash()
            ref = self._registry.push(request.built_image_digest, f"cand-{request.candidate_hash[:12]}")
            if not ref.startswith(self._repo + "@sha256:"):
                raise RuntimeError(f"registry returned an unexpected reference {ref}")
            st.update(attempt_id, registry_ref=ref, state="pushed")
            sdl = self._render(ref)
        except Exception as exc:  # nothing exists on Akash yet
            return self._finish(attempt_id, DeployStatus.FAILED, str(exc)[:500])

        st.update(attempt_id, state="creating")
        try:
            dseq = api.create_deployment(sdl)
        except AkashApiError as exc:
            status = DeployStatus.UNKNOWN if exc.maybe_applied else DeployStatus.FAILED
            return self._finish(attempt_id, status, str(exc))
        st.update(attempt_id, dseq=dseq, state="created")

        leased, error = self._lease(api, dseq)
        if not leased:
            return self._abandon(attempt_id, api, dseq, error)
        st.update(attempt_id, provider=leased, state="leased")

        deadline = self._clock() + self._ready_timeout
        while True:
            try:
                state, uri, _ = self._lease_state(api.deployment(dseq))
            except AkashApiError as exc:
                state, uri = None, None
                last = str(exc)
            else:
                last = f"lease state {state}"
            if uri:
                st.update(attempt_id, uri=uri)
                return self._finish(attempt_id, DeployStatus.ACCEPTED, None)
            if state == "closed":
                return self._finish(attempt_id, DeployStatus.FAILED, "lease closed before the service was ready",
                                    state="closed")
            if self._clock() >= deadline:
                return self._finish(attempt_id, DeployStatus.UNKNOWN,
                                    f"no service URI within {self._ready_timeout:.0f}s ({last}); reconcile later")
            self._sleep(self._poll)

    def _lease(self, api: AkashApi, dseq: str) -> tuple[str | None, str]:
        deadline = self._clock() + self._bid_timeout
        while True:
            try:
                bids = [b["bid"] for b in api.bids(dseq) if b.get("bid", {}).get("state") == "open"]
            except AkashApiError as exc:
                bids, last = [], str(exc)
            else:
                last = "no open bids"
            if bids:
                break
            if self._clock() >= deadline:
                return None, f"no usable bid within {self._bid_timeout:.0f}s ({last})"
            self._sleep(self._poll)
        bids.sort(key=lambda b: float(b.get("price", {}).get("amount", "inf")))
        errors = []
        for bid in bids[:3]:
            bid_id = bid["id"]
            try:
                api.create_lease(dseq, int(bid_id["gseq"]), int(bid_id["oseq"]), bid_id["provider"])
                return bid_id["provider"], ""
            except AkashApiError as exc:
                errors.append(f"{bid_id['provider']}: {exc}")
        return None, "lease failed: " + " | ".join(errors)

    def _abandon(self, attempt_id: str, api: AkashApi, dseq: str, error: str) -> DeployResult:
        try:
            api.close(dseq)
        except AkashApiError as exc:
            return self._finish(attempt_id, DeployStatus.UNKNOWN, f"{error}; closing {dseq} failed: {exc}")
        return self._finish(attempt_id, DeployStatus.FAILED, f"{error}; deployment {dseq} closed", state="closed")

    def _lease_state(self, dep: dict) -> tuple[str | None, str | None, str | None]:
        if dep.get("deployment", {}).get("state") == "closed":
            return "closed", None, None
        for lease in dep.get("leases") or []:
            if lease.get("state") != "active":
                continue
            svc = ((lease.get("status") or {}).get("services") or {}).get(self._service) or {}
            uris = svc.get("uris") or []
            ready = (svc.get("available_replicas") or svc.get("ready_replicas") or 0) >= 1
            return "active", (uris[0] if uris and ready else None), lease.get("id", {}).get("provider")
        return (dep.get("deployment", {}).get("state") or "unknown"), None, None

    def _render(self, ref: str) -> str:
        sdl = self._template.replace("{{IMAGE}}", ref)
        if f'image: "{ref}"' not in sdl:
            raise RuntimeError("SDL template has no image placeholder")
        user, token = self._env.get("GHCR_PULL_USER"), self._env.get("GHCR_PULL_TOKEN")
        if bool(user) != bool(token):
            raise RuntimeError("set both GHCR_PULL_USER and GHCR_PULL_TOKEN, or neither")
        if not user:  # public package: the provider pulls anonymously
            return sdl
        creds = (f'\n    credentials:\n      host: ghcr.io\n      username: {json.dumps(user)}\n'
                 f'      password: {json.dumps(token)}')
        return sdl.replace(f'image: "{ref}"', f'image: "{ref}"{creds}', 1)

    def _akash(self) -> AkashApi:
        if self._api is None:
            self._api = AkashConsoleApi(self._env.get("AKASH_API_KEY"))
        return self._api

    def _finish(self, attempt_id: str, status: DeployStatus, error: str | None, state: str | None = None) -> DeployResult:
        # UNKNOWN keeps the step marker (e.g. "creating") so reconcile() knows how far the attempt got.
        db_state = state or {DeployStatus.ACCEPTED: "accepted", DeployStatus.FAILED: "failed"}.get(status)
        if db_state:
            self._store.update(attempt_id, state=db_state, error=error)
        else:
            self._store.update(attempt_id, error=error)
        if db_state in _TERMINAL:
            self._store.release(attempt_id)
        a = self._store.get(attempt_id)
        ref = f"akash:{a['dseq']}" if a["dseq"] else None
        return self._result(attempt_id, a["registry_ref"] or a["image_id"], ref, status, error)

    def _result(self, attempt_id: str, image: str, ref: str | None, status: DeployStatus,
                error: str | None) -> DeployResult:
        return DeployResult(attempt_id, self._target_id, image, ref, status, error)


def load_connector(target_id: str = "juice-shop", **kwargs) -> AkashDeployConnector:
    target = json.loads((ROOT / "config" / "targets" / f"{target_id}.json").read_text(encoding="utf-8"))
    return AkashDeployConnector(target, **kwargs)


__all__ = ["AkashApiError", "AkashConsoleApi", "AkashDeployConnector", "DockerRegistry", "load_connector"]
