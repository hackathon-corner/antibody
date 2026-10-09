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
