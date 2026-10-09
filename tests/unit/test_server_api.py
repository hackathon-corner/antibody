import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from contracts import Event
from server.app import create_app

T0 = datetime(2026, 10, 9, 20, 2, 33, tzinfo=timezone.utc)


class InMemoryStore:
    """Test double; the production store is ClickHouseEventStore."""

    def __init__(self, events):
        self.events = events

    def ping(self):
        return "test"

    def run_ids(self, limit=50):
        return [("r1", T0)]

    def events_for_run(self, run_id):
        return [e for e in self.events if e.run_id == run_id]


class BrokenStore(InMemoryStore):
    def events_for_run(self, run_id):
        raise ConnectionError("down")


EVENT = Event("evt_1", "r1", None, None, "target.build", "gha", T0, "success", "https://example.invalid/1")


def test_run_events_serialized_with_iso_times():
    client = TestClient(create_app(lambda: InMemoryStore([EVENT])))
    body = client.get("/api/runs/r1/events").json()
    assert body["events"][0]["event_id"] == "evt_1"
    assert body["events"][0]["observed_at"] == "2026-10-09T20:02:33+00:00"


def test_unknown_run_is_404_not_empty_success():
    client = TestClient(create_app(lambda: InMemoryStore([EVENT])))
    assert client.get("/api/runs/nope/events").status_code == 404


def test_store_failures_surface_as_503():
    client = TestClient(create_app(lambda: BrokenStore([EVENT])))
    r = client.get("/api/runs/r1/events")
    assert r.status_code == 503 and "ConnectionError" in r.json()["detail"]

    def no_config():
        raise RuntimeError("missing settings")

    assert TestClient(create_app(no_config)).get("/api/health").status_code == 503


def test_api_has_no_write_routes():
    app = create_app(lambda: InMemoryStore([]))
    methods = {m for route in app.routes for m in getattr(route, "methods", set())}
    assert methods <= {"GET", "HEAD"}


def test_runs_list_reports_timezone_aware_times():
    client = TestClient(create_app(lambda: InMemoryStore([EVENT])))
    assert client.get("/api/runs").json()["runs"] == [{"runId": "r1", "lastObservedAt": "2026-10-09T20:02:33+00:00"}]


def test_dashboard_served_at_root_without_shadowing_api(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>dash</title>")
    client = TestClient(create_app(lambda: InMemoryStore([EVENT]), web_dist=str(tmp_path)))
    assert "dash" in client.get("/").text
    assert client.get("/api/runs").json()["runs"][0]["runId"] == "r1"
    assert client.get("/api/runs/nope/events").status_code == 404
