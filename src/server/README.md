# src/server

Owner: C.

Host API and read-only evidence/report delivery. Host-owned release validation stays outside model control.

Status: read-only evidence API (FastAPI) over the ClickHouse event store.

```
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn server.app:app --app-dir src --port 8000   # needs the ClickHouse values in .env
```

| Route | Returns |
|---|---|
| `GET /api/health` | Evidence-store reachability and version; 503 if unreachable |
| `GET /api/runs` | Recorded run IDs with last observed time |
| `GET /api/runs/{run_id}/events` | Deduplicated events for one run; 404 if none recorded |
| `GET /api/docs` | OpenAPI UI |

No write routes. Store failures return 503 with the error type, never an empty success. CORS origins come from `ANTIBODY_CORS_ORIGINS` (default `http://localhost:5173`).

If `ANTIBODY_WEB_DIST` points at a built dashboard (`src/web/dist`), it is served at `/` from the same process. The deployable image does this: `infra/containers/evidence-api/Dockerfile`, built and pushed by `.github/workflows/build-evidence-api.yml` to `ghcr.io/hackathon-corner/antibody-evidence-api`. It takes the `CLICKHOUSE_*` settings from the host environment; no `.env` is baked in.


## Host runner (`runner.py`)

Owns `Run` state (SQLite, e.g. `runtime/host.db`, which is git-ignored) and is the only path to deployment. It wires A's `RepairAgent`, the scanner, B's build/checks and deploy connector, and the event sink (`ClickHouseEventStore`).
- Transitions follow the PRD §6 state machine, and each emits a `run.state` event with a stable ID.
- Deploy is claimed once per run. A claim with no result after a restart makes the run `unresolved`, never a redeploy.
- A missing Guild session or deploy connector ends the run as `failed` or `unresolved`, with the reason recorded.
- An accepted deploy goes to `verifying`, not `completed`. Only B5's external probe verdict completes a run.
