#!/usr/bin/env node
// Independent behavior checks for the pinned Juice Shop target (owner: B).
// Usage: node tests/e2e/juice-shop-checks.mjs --base-url <url> --mode baseline|candidate [--out <file>]
//
// baseline:  injection-regression passes when the selected injection is REPRODUCED; edge cases are observed only.
// candidate: injection must not leak; ordinary search, edge cases, and the access boundary must match expectations.
// Output never contains the canary credentials or leaked row contents, only booleans, counts, and digests.
// Exit code: 0 all required checks pass, 1 a required check failed, 2 a check errored.

import { createHash, randomBytes } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const fixturePath = join(here, '../fixtures/juice-shop/search-expectations.json')
const suiteFiles = [fileURLToPath(import.meta.url), fixturePath]
const fx = JSON.parse(readFileSync(fixturePath, 'utf8'))

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1]])
  return acc
}, []))
const baseUrl = (args['base-url'] ?? '').replace(/\/$/, '')
const mode = args.mode
if (!baseUrl || !['baseline', 'candidate'].includes(mode)) {
  console.error('usage: --base-url <url> --mode baseline|candidate [--out file]')
  process.exit(2)
}

const sha256 = (s) => createHash('sha256').update(s).digest('hex')
const suiteSha256 = sha256(suiteFiles.map((f) => sha256(readFileSync(f))).join('\n'))
const TIMEOUT_MS = 15000

async function http (path, init = {}) {
  const res = await fetch(baseUrl + path, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) })
  const text = await res.text()
  let json
  try { json = JSON.parse(text) } catch { json = undefined }
  return { status: res.status, text, json, bodySha256: sha256(text) }
}

const search = (q) => http('/rest/products/search?q=' + encodeURIComponent(q))
const sameList = (a, b) => a.length === b.length && a.every((v, i) => v === b[i])
const ids = (r) => Array.isArray(r.json?.data) ? r.json.data.map((p) => p.id) : null

const results = []
async function check (checkId, required, fn) {
  const startedAt = new Date().toISOString()
  let outcome, observed
  try {
    ({ outcome, observed } = await fn())
  } catch (e) {
    outcome = 'error'
    observed = { error: String(e?.message ?? e).slice(0, 300) }
  }
  results.push({ checkId, required, outcome, observed, startedAt, finishedAt: new Date().toISOString() })
}

// Synthetic canary user created per run on the target under test.
const canary = {
  email: `canary-${randomBytes(6).toString('hex')}@antibody.invalid`,
  password: `Cn-${randomBytes(9).toString('hex')}`
}
let token

await check('setup.canary-user', true, async () => {
  const reg = await http('/api/Users', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: canary.email, password: canary.password, passwordRepeat: canary.password, securityQuestion: { id: 1 }, securityAnswer: 'antibody' })
  })
  const login = await http('/rest/user/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: canary.email, password: canary.password })
  })
  token = login.json?.authentication?.token
  return { outcome: reg.status === 201 && token ? 'pass' : 'fail', observed: { registerStatus: reg.status, loginStatus: login.status, tokenIssued: Boolean(token) } }
})

await check('search.ordinary', true, async () => {
  const per = []
  for (const { q, ids: expected } of fx.ordinaryQueries) {
    const r = await search(q)
    const got = ids(r)
    const shapeOk = r.json?.status === 'success' && Array.isArray(r.json?.data) &&
      r.json.data.every((p) => sameList(Object.keys(p).sort(), fx.productKeys))
    per.push({ q, status: r.status, count: got?.length ?? null, idsMatch: got !== null && sameList(got, expected), shapeOk })
  }
  return { outcome: per.every((p) => p.status === 200 && p.idsMatch && p.shapeOk) ? 'pass' : 'fail', observed: per }
})

await check('search.edge-cases', mode === 'candidate', async () => {
  const per = []
  for (const ec of fx.edgeCases) {
    const q = ec.q ?? ec.qRepeat.char.repeat(ec.qRepeat.count)
    const r = await search(q)
    const got = ids(r)
    per.push({ id: ec.id, status: r.status, count: got?.length ?? null, ok: r.status === ec.candidate.status && got !== null && sameList(got, ec.candidate.ids) })
  }
  if (mode === 'baseline') return { outcome: 'observed', observed: per }
  return { outcome: per.every((p) => p.ok) ? 'pass' : 'fail', observed: per }
})

await check('security.injection', true, async () => {
  if (!token) throw new Error('canary user unavailable; cannot evaluate leakage')
  const r = await search(fx.injection.payload)
  const rows = Array.isArray(r.json?.data) ? r.json.data : []
  const canaryLeaked = r.text.includes(canary.email)
  const credentialShapedRows = rows.filter((p) => /@/.test(String(p.name)) && /^[0-9a-f]{32}$/.test(String(p.description))).length
  const leaked = canaryLeaked || credentialShapedRows > 0
  const observed = { status: r.status, rowCount: rows.length, canaryLeaked, credentialShapedRows, bodySha256: r.bodySha256 }
  if (mode === 'baseline') return { outcome: leaked ? 'pass' : 'fail', observed: { ...observed, expectation: 'reproduce' } }
  const declared = r.status === 200 && r.json?.status === 'success' && Array.isArray(r.json?.data)
  return { outcome: !leaked && declared ? 'pass' : 'fail', observed: { ...observed, expectation: 'no-leak, HTTP 200 JSON' } }
})

await check('access.boundary', true, async () => {
  const { endpoint, unauthenticatedStatus, authenticatedStatus } = fx.accessBoundary
  if (!token) throw new Error('canary token unavailable')
  const unauth = await http(endpoint)
  const auth = await http(endpoint, { headers: { authorization: `Bearer ${token}` } })
  const ok = unauth.status === unauthenticatedStatus && auth.status === authenticatedStatus
  return { outcome: ok ? 'pass' : 'fail', observed: { endpoint, unauthenticated: unauth.status, authenticated: auth.status } }
})

const required = results.filter((r) => r.required)
const overall = required.some((r) => r.outcome === 'error') ? 'error' : required.every((r) => r.outcome === 'pass') ? 'pass' : 'fail'
const report = { suite: { id: 'juice-shop-checks', sha256: suiteSha256 }, targetId: fx.targetId, baseUrl, mode, overall, results }
const out = JSON.stringify(report, null, 2)
if (args.out) writeFileSync(args.out, out + '\n')
console.log(out)
process.exit(overall === 'pass' ? 0 : overall === 'fail' ? 1 : 2)
