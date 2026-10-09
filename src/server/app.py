"""Read-only evidence API (owner: C).

Serves recorded `Event` rows from the evidence store. It has no write routes and
no release authority. When the store is unreachable it returns 503 with the
failure, never an empty list that would read as "no evidence".

Run: .venv/bin/uvicorn server.app:app --app-dir src --port 8000

When `ANTIBODY_WEB_DIST` names a built dashboard (`src/web/dist`), it is served at `/`
from the same process, so one container carries both the API and the dashboard.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Callable, Protocol

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from contracts import Event

log = logging.getLogger("antibody.server")


class EventStore(Protocol):
    def ping(self) -> str: ...
    def run_ids(self, limit: int = 50) -> list: ...
    def events_for_run(self, run_id: str) -> list[Event]: ...


def _event_json(event: Event) -> dict:
    data = asdict(event)
    data["observed_at"] = event.observed_at.isoformat()
    return data


def create_app(store_factory: Callable[[], EventStore], web_dist: str | None = None) -> FastAPI:
    app = FastAPI(title="Antibody evidence API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    origins = [o for o in os.environ.get("ANTIBODY_CORS_ORIGINS", "http://localhost:5173").split(",") if o]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=[])

    state: dict[str, EventStore] = {}

    def store() -> EventStore:
        try:
            if "store" not in state:
                state["store"] = store_factory()
            return state["store"]
        except Exception as exc:  # configuration or connection failure
            log.warning("evidence store unavailable: %s", exc)
            raise HTTPException(503, detail=f"evidence store unavailable: {type(exc).__name__}") from exc

    def call(fn, *args):
        s = store()
        try:
            return fn(s, *args)
        except Exception as exc:
            log.warning("evidence store query failed: %s", exc)
            raise HTTPException(503, detail=f"evidence store query failed: {type(exc).__name__}") from exc

    @app.get("/api/health")
    def health() -> dict:
        version = call(lambda s: s.ping())
        return {"status": "ok", "evidenceStore": {"kind": "clickhouse", "version": version}}

    @app.get("/api/runs")
    def runs(limit: int = 50) -> dict:
        limit = max(1, min(limit, 200))
        rows = call(lambda s: s.run_ids(limit))
        return {"runs": [{"runId": r, "lastObservedAt": t.isoformat()} for r, t in rows]}

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: str) -> dict:
        events = call(lambda s: s.events_for_run(run_id))
        if not events:
            raise HTTPException(404, detail="no recorded events for this run")
        return {"runId": run_id, "events": [_event_json(e) for e in events]}

    # Mounted last so /api/* routes take precedence over the static files.
    if web_dist:
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


def _default_store() -> EventStore:
    from adapters.clickhouse_events import ClickHouseEventStore

    return ClickHouseEventStore.from_env()


app = create_app(_default_store, os.environ.get("ANTIBODY_WEB_DIST") or None)
