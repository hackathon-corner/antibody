# Demo script (3 minutes)

Follows the PRD §10 suggested story and acceptance checklist. Assumes **B5 (deploy connector) is complete** by demo time — everything else below is already real and verified as of 2026-10-09. Swap in the final repaired-candidate URL/digest once B5 actually lands; placeholders are marked `<…>`.

Rule: never narrate a step as live if it isn't. If any live step is slow/flaky at demo time, say "recorded run" explicitly and cut to the saved evidence — don't fake it.

---

## 0:00–0:20 — Ordinary search works

Open the **baseline** public deployment (unrepaired, intentionally vulnerable):

```
https://o7ne4et1e5duvff3f1697lr794.ingress.h6i-dedicated.eu-se-1.digitalfrontier.so
```

Say: *"This is our own deployment of OWASP Juice Shop, source-built and pinned to a specific commit. Ordinary search works — searching 'apple' returns real products."*

Type `apple` in the search box, or hit directly:
```
curl "<baseline-url>/rest/products/search?q=apple"
```

---

## 0:20–0:45 — The baseline security failure

Say: *"But the search endpoint has a real SQL injection — not a toy example, a genuine unparameterized query."*

```
curl "<baseline-url>/rest/products/search?q=xyz')) OR 1=1--"
```

Point out the response leaks far more rows than a normal search would (per B's recorded probe: 24 credential-shaped rows, vs. 0 for a legitimate empty-match query). *"This is the exact defect our agent is going to find and fix — not staged, the real upstream Juice Shop bug."*

---

## 0:45–1:15 — Start the repair agent: Semgrep finds it, Guild fixes it

Say: *"The agent's first step is a real Semgrep scan against the pinned source."*

```
python scripts/target.py source --out runtime/source
bash scripts/semgrep-scan.sh runtime/source /tmp/out.json
```
→ one finding, `routes/search.ts:23`, rule `express-sequelize-injection`, 0 scan errors.

Say: *"That finding goes to a real Guild AI agent session — not a canned response."*

Show the Guild session (either live, or the recorded one: session `01a12282-589d-f268-0000-79a97f4219f6`, visible at its `session_url` in the Guild dashboard). The agent returns a real unified diff: it replaces the string-interpolated query with Sequelize's `replacements` parameter binding.

---

## 1:15–1:40 — Independent checks, run by someone else's code

Say: *"The candidate doesn't get trusted just because the model produced it. It goes through B's isolated worker — host-validated scope, built in a sandboxed container, run against an independent check suite the agent never sees."*

Show the real recorded result: the operator-tested repair passed all 5 required checks (ordinary search × 6 queries, edge cases, injection regression, access boundary) — candidate hash, image digest, and suite hash all recorded.

---

## 1:40–2:10 — Open the deployed candidate, verify live

Say: *"This exact candidate — same hash, same image digest — is now serving publicly."*

Open the **repaired** deployment:
```
<repaired-candidate-url>
```

1. Ordinary search still works: `?q=apple` → same real products.
2. The attack no longer works: `?q=xyz')) OR 1=1--` → no leak, matches the "candidate" expectation (0 extra rows).

*"Same external probe script we ran against the baseline, now run against the fix — and it passes."*

---

## 2:10–2:30 — Show a rejected bad candidate

Say: *"The gate isn't just vibes — here's what happens when something bad gets submitted through the same path."*

Pick one live:
```
pytest tests/unit/test_adversarial_candidate.py -v
```
— shows both rejection modes: a scope-violating patch (touches a forbidden file) rejected before any check runs, and a "closed the hole by closing the business" patch (search returns nothing) that passes scope but fails the independent behavior checks and is blocked from deploy.

Or point to B's real recorded case: the `WHERE 1=0` mutant — passes the injection check (nothing leaks because nothing *works*) but correctly fails `search.ordinary`, rejected.

*"Its origin is disclosed honestly — labeled as an operator-supplied test candidate, never attributed to the model."*

---

## 2:30–3:00 — Report, evidence, sponsors

Open the evidence dashboard:
```
http://d0ischq47pee1b61pmtjbh3ido.ingress.h6i-dedicated.eu-se-1.digitalfrontier.so
```

Show `/api/runs` and a run's `/api/runs/<id>/events` — real ClickHouse-backed event history, not a mockup.

Close: *"Five sponsor tools actually exercised: Guild AI ran the real repair session, Semgrep produced the real finding, ClickHouse stores the real evidence, Senso supplied real source-linked remediation guidance, and the whole thing is deployed on Akash — both the vulnerable baseline and the fix, plus this dashboard. The report says these checks passed for this revision — not that the application is secure. Juice Shop still has other intentional vulnerabilities; we fixed one, honestly, and proved it."*

---

## Fallback notes

- If Guild's session is slow live (known 30–60s accept latency), narrate through it and cut to the saved diff/session ID above rather than waiting on stage.
- If the repaired-candidate deployment isn't up yet at demo time, show the baseline's injection live, then the *recorded* repaired-candidate probe output, clearly labeled "recorded run, not live" — per PRD §10, this is acceptable, fabricating one is not.
- Sponsor count already clears the "at least three" bar (Guild, Semgrep, ClickHouse) even without Senso/Akash, so losing any one non-core sponsor live doesn't break acceptance criterion 9.
