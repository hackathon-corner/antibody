# Builder B checklist: target, independent verification, deployment

Owner: B. Task IDs and "done when" criteria come from [PRD §8](../PRD.md#builder-b--target-independent-checks-and-deployment). Tick a box only when its result has actually been observed. Put evidence (digest, URL, run ID) next to the item.

Stack: Python 3.11+ (stdlib first) for B's Python code, Docker for target builds. The independent check suite is Node with no dependencies (`tests/e2e/juice-shop-checks.mjs`; see Q5 in [collab.md](../collab.md)). Juice Shop stays Node inside its container.

## Status (updated 2026-10-09, at `c29b691`)

| Task | State | Blocking |
|---|---|---|
| B1 | Pins done; Docker now works locally; baseline image not yet built, digest not recorded | Nothing. Next action. |
| B2 | Modified source builds and pushes to GHCR in CI; not public | Public host choice and pull access (Q6) |
| B3 | Suite and expectations written and verified against the upstream release package | Re-observe on the source-built baseline; record the suite hash |
| B4 | Not started | Nothing (B3 is usable). **A5 waits on this, and A's Guild blocker is resolved, so real candidates are close.** |
| B5 | Not started | B2, B4. A6 waits on this. |
| B6 | Not started | B4 (A4 is done) |
| B7 | Stretch | B5 |

PRD checkpoint "first 40 minutes" (a modified source build reaches a public endpoint) is **missed**. B2 and B4 are now the team's critical path.

## Next actions (in order)

1. `python scripts/target.py build` for the baseline (now applies `build-fixes/` like CI). Record `baseline_image_digest`; `run` + `smoke`; run the suite in baseline mode against it. Closes B1.
2. Answer Q5 and Q6 in [collab.md](../collab.md): keep the `.mjs` suite (recommended), pick the public host, choose the image pull method (read-only token preferred over a public package).
3. Build B4 around `juice-shop-checks.mjs`, emitting `CheckResult` with `image_digest` and `suite_hash`, so A can run real candidates.
4. Deploy a source-built digest to the public host and fetch it from outside. Closes B2.
5. Implement `DeployConnector.deploy(request)` for `src/server/runner.py` (B5).

## 0. Workstation and access

- [x] Python 3.11+ installed (3.12.10 via winget, 2026-10-09). Open a new shell so it's on PATH.
- [x] Docker Desktop installed and running (engine 29.8.1 on WSL2, verified 2026-10-09)
- [ ] Public host chosen: Akash or a fallback we're authorized to use (Q6)
- [x] Container registry push from CI: `build-target` pushes to `ghcr.io/hackathon-corner/antibody-target` (private) with the workflow token
- [ ] Registry push from B's machine, if local builds are to be deployed (otherwise deploy CI-built digests)
- [ ] Registry pull access for the public host (read-only token) (Q6)
- [ ] Team fork of Juice Shop. Decision 0002 says no fork is needed for the build path; decide whether to keep this item. If kept: `source.repo` updated, commit unchanged.

## B1. Pin source/image, start target, synthetic baseline data

- [x] Upstream commit pinned: `v20.2.0` / `5658473cf8814459bf89000ce373b20ed0b4eb37` ([decision 0001](../decisions/0001-target-pin.md), [decision 0002](../decisions/0002-target-pin-and-checks.md))
- [x] Base images pinned by digest (git, `node:24`, distroless `nodejs24-debian13`)
- [x] Target config written: `config/targets/juice-shop.json` (one snake_case schema, shared with the spike scripts since `5825583`)
- [x] Dockerfile written: `infra/containers/juice-shop/Dockerfile`
- [x] Target script written: `scripts/target.py` (source / build / run / smoke / stop)
- [x] Host-owned build fix for floating dependencies: `infra/containers/build-fixes/frontend-sbom.patch` ([run 37982608827](https://github.com/hackathon-corner/antibody/actions/runs/37982608827)); applied by both CI and the local Dockerfile (`c29b691`)
- [ ] `python scripts/target.py source --out runtime/source` runs; `routes/search.ts` hash matches the one in `config/targets/README.md`
- [ ] Baseline image built from source: `python scripts/target.py build`
- [ ] `baseline_image_digest` recorded in `config/targets/juice-shop.json`
- [ ] Source-built baseline runs and `smoke` returns products for `q=apple`. (Observed so far only on the upstream release package, darwin/arm64, by C.)
- [ ] Confirmed only Juice Shop's bundled fictional seed data is in use
- [x] A told the pin is ready (`18348ca`; acknowledged in [plan-for-A.md](../plan-for-A.md))
- [x] A told about upstream answer files `data/static/codefixes/unionSqlInjectionChallenge_*` (collab Q4; A excludes them from agent context, C's `src/server/answer_match.py` flags exact matches)
- [ ] Decide `targetId` in `tests/fixtures/juice-shop/search-expectations.json` (`juice-shop-v20.2.0`) vs `target_id` in the target config (`juice-shop`); check reports carry the fixture's value

## Contract review with A (before B4/B5)

- [x] `CheckResult` gets `image_digest` and `suite_hash` (collab Q7; `src/contracts/models.py`, both optional)
- [x] `Observation.release_ref` becomes `str | None` (collab Q7)
- [ ] Release/check interfaces agreed with A and C. The runner (`src/server/runner.py`, C) already defines `DeployConnector.deploy(DeployRequest) -> DeployResult` and a `build_candidate(Candidate) -> image digest` callable; confirm these are B's interfaces.

## B2. Prove rebuilt-image public deployment (target: first ~40 min)

- [x] Build with a trivial harmless patch and push it to the registry: `spike-marker.patch` via `build-target`, image `ghcr.io/hackathon-corner/antibody-target@sha256:2b20151b…` (full digest in the run output, [run 37983610899](https://github.com/hackathon-corner/antibody/actions/runs/37983610899))
- [ ] Deploy that digest to the public host; definition goes in `infra/akash/` or `infra/containers/`
- [ ] External HTTP fetch, from outside this machine, shows the rebuilt image serving search (the marker app name is visible)
- [ ] If Juice Shop can't be deployed promptly: escalate per PRD §9 (smaller attributed target, disclosed)

## B3. Baseline exploit and functionality checks (before A's first candidate)

Suite written by C in the spike; B owns it from here.

- [x] Suite in `tests/e2e/juice-shop-checks.mjs`: ordinary search (6 queries, exact product ID order and keys)
- [x] Edge cases: single quote, double quote, over-limit input (baseline: quote → HTTP 500, the defect)
- [x] Injection probe with a per-run synthetic canary user; output carries only booleans, counts and digests
- [x] Protected endpoint: `/api/Users` 401 unauthenticated, 200 authenticated
- [x] Expected results recorded in `tests/fixtures/juice-shop/search-expectations.json` (from the upstream release package, not a source-built image)
- [x] Negative controls observed: candidate mode fails on the unrepaired baseline; a `WHERE 1=0` mutant fails `search.ordinary` ([decision 0002](../decisions/0002-target-pin-and-checks.md))
- [ ] Re-run in baseline mode against the source-built baseline image and confirm the expectations hold
- [ ] Suite hash recorded somewhere fixed (the suite computes it at run time as `suite.sha256`; the CI output records it as `suiteSha256`)
- [ ] Definitions out of the agent's reach (the validator only allows `routes/search.ts`; confirm the worker reads the suite from the host checkout, not from the candidate)
- [ ] Q5 answered: keep `.mjs` or port to Python (keep fixture file and check IDs either way)

## B4. Isolated candidate verification worker

- [ ] Independent change-scope check: only `routes/search.ts`, rejected before build (reuse or mirror `src/agent/validator.py`)
- [ ] Builds the candidate with no secrets and restricted network, with bounded CPU, memory and time
- [ ] Runs the B3 suite in candidate mode; emits `CheckResult` tied to candidate hash, image digest and suite hash
- [ ] An error or unknown result blocks release (suite exit code 2 = error)
- [ ] Plug into the runner's `build_candidate` and A's `run_checks`

## B5. Fixed deployment connector and external verification

- [ ] `DeployConnector.deploy(request)` for `src/server/runner.py`: candidate hash and image digest only; no arbitrary host, URL, command or `latest` tag
- [ ] Deployments serialized; durable state; reconciles with the host after a restart or timeout (the runner's `RunStore.claim_deploy` already records claims; the connector must reconcile with the host's actual state)
- [ ] Emits `DeployResult`; acceptance by the host is not treated as proof the image is serving
- [ ] External probes repeat the search and injection checks and emit `Observation`

## B6. Bad-candidate tests (with A)

- [ ] Candidate that breaks search is rejected by the same gate (start from the `WHERE 1=0` mutant)
- [ ] Candidate that edits tests or forbidden paths is rejected before build
- [ ] A legitimate repair passes; each candidate's origin is labeled accurately (supplied mutants are labeled as supplied, never as model output)

## B7. Stretch: stable alias and recovery

- [ ] Promote behind a stable alias, then recover to the previous revision, both tied to exact digests
- [ ] Restoring a vulnerable baseline is not described as a security fix
