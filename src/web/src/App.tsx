import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type EvidenceEvent, type Health, type RunSummary } from './api'

type Load<T> = { state: 'loading' } | { state: 'ok'; data: T } | { state: 'error'; status?: number; message: string }

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): [Load<T>, () => void] {
  const [value, setValue] = useState<Load<T>>({ state: 'loading' })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let live = true
    setValue({ state: 'loading' })
    fn().then(
      (data) => live && setValue({ state: 'ok', data }),
      (e: unknown) =>
        live &&
        setValue({
          state: 'error',
          status: e instanceof ApiError ? e.status : undefined,
          message: e instanceof Error ? e.message : String(e),
        }),
    )
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return [value, useCallback(() => setTick((t) => t + 1), [])]
}

// Outcome strings are recorded as-is; only well-known values get a colour, everything else is shown neutrally.
function tone(outcome: string): 'ok' | 'bad' | 'warn' {
  const o = outcome.toLowerCase()
  if (['success', 'pass', 'passed', 'accepted', 'completed'].includes(o)) return 'ok'
  if (['failure', 'fail', 'failed', 'rejected', 'blocked'].includes(o)) return 'bad'
  return 'warn'
}

const fmtTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' })

const short = (s: string | null, n = 12) => (s ? (s.length > n ? s.slice(0, n) + '…' : s) : '—')

function selectedRunFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get('run')
}

export default function App() {
  const [health, reloadHealth] = useLoad<Health>(api.health, [])
  const [runs, reloadRuns] = useLoad<RunSummary[]>(api.runs, [])
  const [chosenRunId, setRunId] = useState<string | null>(selectedRunFromUrl())
  const runId = chosenRunId ?? (runs.state === 'ok' && runs.data.length ? runs.data[0].runId : null)

  useEffect(() => {
    const onPop = () => setRunId(selectedRunFromUrl())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const choose = (id: string) => {
    setRunId(id)
    window.history.pushState(null, '', `?run=${encodeURIComponent(id)}`)
  }

  const refresh = () => {
    reloadHealth()
    reloadRuns()
  }

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Antibody evidence</h1>
          <p className="sub">Recorded events only. Nothing here is inferred or sample data.</p>
        </div>
        <div className="top-right">
          <StoreStatus health={health} />
          <button onClick={refresh}>Refresh</button>
        </div>
      </header>

      <main className="layout">
        <aside className="runs">
          <h2>Runs</h2>
          {runs.state === 'loading' && <p className="muted">Loading…</p>}
          {runs.state === 'error' && <ErrorBox load={runs} />}
          {runs.state === 'ok' && runs.data.length === 0 && <p className="muted">No runs recorded yet.</p>}
          {runs.state === 'ok' && (
            <ul>
              {runs.data.map((r) => (
                <li key={r.runId}>
                  <button className={r.runId === runId ? 'run active' : 'run'} onClick={() => choose(r.runId)}>
                    <span className="mono">{r.runId}</span>
                    <span className="muted small">{fmtTime(r.lastObservedAt)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="detail">{runId ? <RunEvents runId={runId} /> : <p className="muted">Select a run.</p>}</section>
      </main>
    </div>
  )
}

function StoreStatus({ health }: { health: Load<Health> }) {
  if (health.state === 'loading') return <span className="pill warn">Evidence store: checking</span>
  if (health.state === 'error')
    return (
      <span className="pill bad" title={health.message}>
        Evidence store unavailable{health.status ? ` (${health.status})` : ''}
      </span>
    )
  return (
    <span className="pill ok">
      {health.data.evidenceStore.kind} {health.data.evidenceStore.version}
    </span>
  )
}

function ErrorBox({ load }: { load: { status?: number; message: string } }) {
  return (
    <div className="error">
      <strong>{load.status ? `HTTP ${load.status}` : 'Request failed'}</strong>
      <span>{load.message}</span>
    </div>
  )
}

function RunEvents({ runId }: { runId: string }) {
  const [events] = useLoad<EvidenceEvent[]>(() => api.events(runId), [runId])
  return (
    <>
      <h2 className="mono">{runId}</h2>
      {events.state === 'loading' && <p className="muted">Loading…</p>}
      {events.state === 'error' &&
        (events.status === 404 ? <p className="muted">No events recorded for this run.</p> : <ErrorBox load={events} />)}
      {events.state === 'ok' && (
        <table>
          <thead>
            <tr>
              <th>Observed (local)</th>
              <th>Event</th>
              <th>Outcome</th>
              <th>Emitter</th>
              <th>Candidate</th>
              <th>Release</th>
              <th>Artifact</th>
            </tr>
          </thead>
          <tbody>
            {events.data.map((e) => (
              <tr key={e.event_id} title={e.event_id}>
                <td className="nowrap">{fmtTime(e.observed_at)}</td>
                <td className="mono">{e.event_type}</td>
                <td>
                  <span className={`pill ${tone(e.outcome)}`}>{e.outcome}</span>
                </td>
                <td className="mono small">{e.emitter}</td>
                <td className="mono small">{short(e.candidate_hash)}</td>
                <td className="mono small">{short(e.release_ref)}</td>
                <td className="small">
                  {e.artifact_ref?.startsWith('https://') ? (
                    <a href={e.artifact_ref} target="_blank" rel="noreferrer">
                      open
                    </a>
                  ) : (
                    short(e.artifact_ref, 24)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
