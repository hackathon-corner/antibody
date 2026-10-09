import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from adapters.akash_deploy import AkashApiError, AkashDeployConnector
from adapters.check_worker import suite_hash
from contracts import DeployRequest, DeployStatus

ROOT = Path(__file__).resolve().parents[2]
TARGET = json.loads((ROOT / "config" / "targets" / "juice-shop.json").read_text(encoding="utf-8"))
REPO = TARGET["deploy"]["registry_repo"]
H = "a" * 64
IMAGE = "sha256:" + "e" * 64
PUSHED = f"{REPO}@sha256:" + "f" * 64
ENV = {"GHCR_PULL_USER": "puller", "GHCR_PULL_TOKEN": "ghp_secret_token", "AKASH_API_KEY": "k"}


class FakeRegistry:
    def __init__(self, ref=PUSHED, error=None):
        self.ref, self.error, self.pushed = ref, error, []

    def push(self, image_id, tag):
        self.pushed.append((image_id, tag))
        if self.error:
            raise RuntimeError(self.error)
        return self.ref


class FakeAkash:
    def __init__(self, bids=None, create_error=None, lease_error=None, ready_after=0, close_error=None):
        self.sdls, self.leases, self.closed, self.polls = [], [], [], 0
        self._bids = bids if bids is not None else [bid("p-cheap", "1.0"), bid("p-dear", "5.0")]
        self.create_error, self.lease_error, self.close_error = create_error, lease_error, close_error
        self.ready_after = ready_after

    def create_deployment(self, sdl):
        self.sdls.append(sdl)
        if self.create_error:
            raise self.create_error
        return "12345"

    def bids(self, dseq):
        return self._bids

    def create_lease(self, dseq, gseq, oseq, provider):
        if self.lease_error:
            raise self.lease_error
        self.leases.append(provider)
        return {}

    def deployment(self, dseq):
        self.polls += 1
        if dseq in self.closed:
            return {"deployment": {"state": "closed"}, "leases": []}
        ready = self.leases and self.polls > self.ready_after
        svc = {"available_replicas": 1, "uris": ["abc.ingress.example"]} if ready else {"available_replicas": 0}
        return {"deployment": {"state": "active"},
                "leases": [{"id": {"provider": "p-cheap"}, "state": "active", "status": {"services": {"juice-shop": svc}}}]}

    def close(self, dseq):
        if self.close_error:
            raise self.close_error
        self.closed.append(dseq)


def bid(provider, amount):
    return {"bid": {"id": {"gseq": 1, "oseq": 1, "provider": provider}, "state": "open",
                    "price": {"denom": "uakt", "amount": amount}}}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def record(tmp_path, passed=True, image=IMAGE, suite=None, h=H):
    d = tmp_path / "checks" / h[:12]
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(json.dumps({"candidate_hash": h, "image_id": image, "passed": passed,
                                               "suite_hash": suite or suite_hash()}))


def connector(tmp_path, api=None, registry=None, env=ENV, **kw):
    clock = Clock()
    return AkashDeployConnector(TARGET, api=api or FakeAkash(), registry=registry or FakeRegistry(),
                                runtime_dir=tmp_path, env=env, sleep=clock.sleep, clock=clock,
                                bid_timeout=60, ready_timeout=120, poll_interval=10, **kw)


def req(h=H, image=IMAGE):
    return DeployRequest("run1", h, image)


def test_accepted_deploys_registry_digest_with_credentials_and_cheapest_bid(tmp_path):
    api, reg = FakeAkash(ready_after=2), FakeRegistry()
    record(tmp_path)
    c = connector(tmp_path, api, reg)
    result = c.deploy(req())
    assert result.status == DeployStatus.ACCEPTED, result.error
    assert result.image_digest == PUSHED and result.release_ref == "akash:12345"
    assert reg.pushed == [(IMAGE, f"cand-{H[:12]}")]
    assert api.leases == ["p-cheap"]
    sdl = api.sdls[0]
    assert f'image: "{PUSHED}"' in sdl and "credentials:" in sdl and "ghp_secret_token" in sdl
    assert c.endpoint(result.attempt_id) == "http://abc.ingress.example"


def test_credentials_never_reach_the_store(tmp_path):
    record(tmp_path)
    connector(tmp_path).deploy(req())
    assert b"ghp_secret_token" not in (tmp_path / "deploy" / "akash.sqlite").read_bytes()


@pytest.mark.parametrize("h,image,setup,needle", [
    ("A" * 64, IMAGE, None, "64 lowercase hex"),
    (H, "ghcr.io/x:latest", None, "exact sha256 digest"),
    (H, IMAGE, "none", "no readable verification record"),
    (H, IMAGE, "failed", "did not pass"),
    (H, "sha256:" + "d" * 64, "ok", "not the image the checks ran against"),
    (H, IMAGE, "stale-suite", "check suite changed"),
])
def test_unverified_requests_are_refused_before_anything_happens(tmp_path, h, image, setup, needle):
    if setup == "failed":
        record(tmp_path, passed=False)
    elif setup == "ok":
        record(tmp_path)
    elif setup == "stale-suite":
        record(tmp_path, suite="0" * 64)
    api, reg = FakeAkash(), FakeRegistry()
    result = connector(tmp_path, api, reg).deploy(req(h, image))
    assert result.status == DeployStatus.FAILED and needle in result.error
    assert reg.pushed == [] and api.sdls == []


def test_public_package_deploys_without_credentials(tmp_path):
    record(tmp_path)
    api = FakeAkash()
    result = connector(tmp_path, api, env={"AKASH_API_KEY": "k"}).deploy(req())
    assert result.status == DeployStatus.ACCEPTED
    assert "credentials:" not in api.sdls[0]


def test_half_set_pull_credentials_fail_before_akash(tmp_path):
    record(tmp_path)
    api = FakeAkash()
    result = connector(tmp_path, api, env={"AKASH_API_KEY": "k", "GHCR_PULL_USER": "u"}).deploy(req())
    assert result.status == DeployStatus.FAILED and "GHCR_PULL_TOKEN" in result.error
    assert api.sdls == []


def test_push_failure_is_failed_not_unknown(tmp_path):
    record(tmp_path)
    result = connector(tmp_path, registry=FakeRegistry(error="denied")).deploy(req())
    assert result.status == DeployStatus.FAILED and "denied" in result.error


def test_create_with_no_answer_is_unknown_and_blocks_the_next_deploy(tmp_path):
    record(tmp_path)
    c = connector(tmp_path, FakeAkash(create_error=AkashApiError(None, "timed out")))
    first = c.deploy(req())
    assert first.status == DeployStatus.UNKNOWN
    second = c.deploy(req())
    assert second.status == DeployStatus.UNKNOWN and "reconcile first" in second.error


def test_create_rejected_by_api_is_failed(tmp_path):
    record(tmp_path)
    result = connector(tmp_path, FakeAkash(create_error=AkashApiError(400, "bad sdl"))).deploy(req())
    assert result.status == DeployStatus.FAILED


def test_no_bids_closes_the_deployment(tmp_path):
    record(tmp_path)
    api = FakeAkash(bids=[])
    result = connector(tmp_path, api).deploy(req())
    assert result.status == DeployStatus.FAILED and "no usable bid" in result.error
    assert api.closed == ["12345"]


def test_no_bids_and_close_fails_is_unknown(tmp_path):
    record(tmp_path)
    api = FakeAkash(bids=[], close_error=AkashApiError(None, "down"))
    assert connector(tmp_path, api).deploy(req()).status == DeployStatus.UNKNOWN


def test_service_never_ready_is_unknown_then_reconciled(tmp_path):
    record(tmp_path)
    api = FakeAkash(ready_after=10_000)
    c = connector(tmp_path, api)
    first = c.deploy(req())
    assert first.status == DeployStatus.UNKNOWN and "reconcile later" in first.error
    api.ready_after = 0
    [reconciled] = c.reconcile()
    assert reconciled.status == DeployStatus.ACCEPTED and reconciled.attempt_id == first.attempt_id
    assert c.deploy(req()).status == DeployStatus.ACCEPTED  # coordinator released


def test_reconcile_after_crash_reads_akash_state_and_never_redeploys(tmp_path):
    record(tmp_path)
    api = FakeAkash(ready_after=10_000)
    c = connector(tmp_path, api)
    first = c.deploy(req())
    api.closed.append("12345")
    restarted = connector(tmp_path, api)
    [r] = restarted.reconcile()
    assert r.status == DeployStatus.FAILED and "closed" in r.error
    assert len(api.sdls) == 1


def test_reconcile_create_without_dseq_stays_unknown(tmp_path):
    record(tmp_path)
    c = connector(tmp_path, FakeAkash(create_error=AkashApiError(503, "busy")))
    c.deploy(req())
    [r] = c.reconcile()
    assert r.status == DeployStatus.UNKNOWN and "Akash Console" in r.error


def test_observe_probes_the_accepted_endpoint_with_the_lease_reference(tmp_path):
    record(tmp_path)
    c = connector(tmp_path)
    result = c.deploy(req())
    seen = []

    def fetch(url):
        seen.append(url)
        return 503, b"unavailable"

    ok, obs = c.observe(result.attempt_id, fetch=fetch)
    assert not ok and obs and all(o.release_ref == "akash:12345" for o in obs)
    assert all(u.startswith("http://abc.ingress.example/") for u in seen)


def test_observe_refuses_an_attempt_without_an_accepted_endpoint(tmp_path):
    record(tmp_path)
    c = connector(tmp_path, FakeAkash(bids=[]))
    result = c.deploy(req())
    with pytest.raises(RuntimeError, match="no accepted public endpoint"):
        c.observe(result.attempt_id)


class SeqAkash(FakeAkash):
    """Hands out a new dseq per deployment."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.n = 100

    def create_deployment(self, sdl):
        super().create_deployment(sdl)
        self.n += 1
        return str(self.n)


def test_recover_redeploys_the_earlier_release_by_digest_and_closes_the_live_one(tmp_path):
    h2, image2 = "b" * 64, "sha256:" + "c" * 64
    record(tmp_path)
    record(tmp_path, h=h2, image=image2)
    api, reg = SeqAkash(), FakeRegistry()
    c = connector(tmp_path, api, reg)
    first = c.deploy(req())
    reg.ref = f"{REPO}@sha256:" + "9" * 64
    second = c.deploy(req(h2, image2))
    assert first.status == second.status == DeployStatus.ACCEPTED
    c.close(first.attempt_id)  # rolled forward: only the second release is live

    back = c.recover(first.attempt_id)
    assert back.status == DeployStatus.ACCEPTED, back.error
    assert back.image_digest == PUSHED, "restores the exact earlier registry digest"
    assert len(reg.pushed) == 2, "recovery does not push again"
    assert f'image: "{PUSHED}"' in api.sdls[-1]
    assert second.release_ref.split(":")[1] in api.closed
    assert [a["attempt_id"] for a in c.live()] == [back.attempt_id]


def test_recover_refuses_an_attempt_that_was_never_accepted(tmp_path):
    record(tmp_path)
    c = connector(tmp_path, FakeAkash(bids=[]))
    failed = c.deploy(req())
    result = c.recover(failed.attempt_id)
    assert result.status == DeployStatus.FAILED and "never an accepted release" in result.error
