// Client for the read-only evidence API (src/server/app.py). Shapes mirror contracts.Event.

export type EvidenceEvent = {
  event_id: string
  run_id: string
  candidate_hash: string | null
  release_ref: string | null
  event_type: string
  emitter: string
  observed_at: string
  outcome: string
  artifact_ref: string | null
}

export type RunSummary = { runId: string; lastObservedAt: string }
export type Health = { status: string; evidenceStore: { kind: string; version: string } }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, { headers: { accept: 'application/json' } })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, String(detail))
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => get<Health>('/api/health'),
  runs: () => get<{ runs: RunSummary[] }>('/api/runs').then((r) => r.runs),
  events: (runId: string) =>
    get<{ events: EvidenceEvent[] }>(`/api/runs/${encodeURIComponent(runId)}/events`).then((r) => r.events),
}
