# src/web

Owner: C.

Run dashboard and evidence UI driven by actual records.

Status: React + TypeScript (Vite) evidence dashboard. It shows evidence-store health, recorded runs, and each run's event timeline from the read-only API. It has no sample data. API errors are shown as errors, and a 404 shows as "no events recorded".

```
# terminal 1 (repo root): evidence API on :8000, needs ClickHouse values in .env
.venv/bin/uvicorn server.app:app --app-dir src --port 8000
# terminal 2
cd src/web && npm install && npm run dev     # http://localhost:5173 (proxies /api to :8000)
npm run build                                # static bundle in dist/; set VITE_API_BASE if the API is on another origin
```
