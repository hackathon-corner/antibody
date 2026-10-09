# Builder B checklist: target, independent verification, deployment

Owner: B. Task IDs and "done when" criteria come from [PRD §8](../PRD.md#builder-b--target-independent-checks-and-deployment). Tick a box only when its result has actually been observed. Put evidence (digest, URL, run ID) next to the item.

Stack: Python 3.11+ (stdlib first) for B's Python code, Docker for target builds. The independent check suite is Node with no dependencies (`tests/e2e/juice-shop-checks.mjs`; see Q5 in [collab.md](../collab.md)). Juice Shop stays Node inside its container.

## Status (updated 2026-10-09, at `54cbd3a`)

| Task | State | Blocking |
|---|---|---|
| B1 | Baseline built from source, local image ID recorded, smoke and injection reproduced | Confirm seed data; `targetId` naming |
| B2 | Spike image in GHCR (now public, anonymous pull confirmed 200); Akash chosen; SDL rendered for the spike digest; lease created but returning 404 | Diagnose the lease (image pull vs container start vs ingress) via Akash console Events/Logs, then re-probe |
| B3 | Suite and expectations written and verified against the upstream release package | Re-observe on the source-built baseline; record the suite hash |
| B4 | Worker written and verified end-to-end on a supplied repair (`src/adapters/check_worker.py`) | A wires `run_checks`; negative control through the worker still to run |
| B5 | Not started | B2, B4. A6 waits on this. |
| B6 | Not started | B4 (A4 is done) |
| B7 | Stretch | B5 |

PRD checkpoint "first 40 minutes" (a modified source build reaches a public endpoint) is **missed**. B2 and B4 are now the team's critical path.

## Next actions (in order)

1. **B2 status (C, 2026-10-09 22:15 UTC):** Juice Shop lease created from C's console with `runtime/akash/juice-shop-2b20151b193d.sdl.yaml`: http://2miicioqlpc819lmuamul59oqg.ingress.froggy-servers.com . `probe_public.py` run from outside at 22:11 UTC **failed**: both probes 404, served by the provider's nginx (no route to the app), still 404 after polling 4 min. Not yet known whether the image pull, the container start, or the ingress is the problem; next step is the lease's Events/Logs in the Akash console. Once it serves, re-run from outside: `python scripts/probe_public.py --url <lease URL> --mode baseline --expect-name "OWASP Juice Shop (Antibody build spike)" --release-ref sha256:2b20151b…` (`baseline`: the spike is unrepaired, so the injection must reproduce) and record the output here. Closes B2.
2. B5 first real run: set `AKASH_API_KEY` (C's Console account) and `docker login ghcr.io` (write:packages), deploy a passing candidate with `load_connector().deploy(...)`, then `observe(attempt_id)`. Confirms whether the Console API reports service URIs.

## 0. Workstation and access

- [x] Python 3.11+ installed (3.12.10 via winget, 2026-10-09). Open a new shell so it's on PATH.
- [x] Docker Desktop installed and running (engine 29.8.1 on WSL2, verified 2026-10-09)
- [x] Public host chosen: Akash, from C's console account (Q6, 2026-10-09)
- [x] Container registry push from CI: `build-target` pushes to `ghcr.io/hackathon-corner/antibody-target` (private) with the workflow token
- [ ] Registry push from the host machine: **needed**, because the B5 connector pushes the locally verified image (`cand-<hash12>`) and deploys it by registry digest. Run `docker login ghcr.io` with a token that has `write:packages` (Docker keeps it in its credential store, never in this repo). Not done: Docker on B's machine has no `ghcr.io` login (2026-10-09). Tick after the first successful connector push
- [ ] Registry pull access for the public host (Q6). Both packages are now public (API reports `public`, anonymous pull token 200, rechecked by B 2026-10-09 after A's note), so no pull credentials are needed. **Update (C, 2026-10-09 22:15 UTC):** `antibody-target` is pullable anonymously (manifest for `sha256:2b20151b…` returns 200 without credentials), so the Juice Shop lease was created with no registry credentials. Tick when a lease has actually pulled the image.
- [x] Team fork of Juice Shop: **dropped** (B, 2026-10-09). Per decision 0002, builds fetch the pinned upstream commit and apply patches, so no fork is needed. `source.repo` stays upstream

## B1. Pin source/image, start target, synthetic baseline data

- [x] Upstream commit pinned: `v20.2.0` / `5658473cf8814459bf89000ce373b20ed0b4eb37` ([decision 0001](../decisions/0001-target-pin.md), [decision 0002](../decisions/0002-target-pin-and-checks.md))
- [x] Base images pinned by digest (git, `node:24`, distroless `nodejs24-debian13`)
- [x] Target config written: `config/targets/juice-shop.json` (one snake_case schema, shared with the spike scripts since `5825583`)
- [x] Dockerfile written: `infra/containers/juice-shop/Dockerfile`
- [x] Target script written: `scripts/target.py` (source / build / run / smoke / stop)
- [x] Host-owned build fix for floating dependencies: `infra/containers/build-fixes/frontend-sbom.patch` ([run 37982608827](https://github.com/hackathon-corner/antibody/actions/runs/37982608827)); applied by both CI and the local Dockerfile (`c29b691`)
- [x] `python scripts/target.py source --out runtime/source` runs; `routes/search.ts` hash matches the one in `config/targets/README.md` (`de09bfc4…`, 2026-10-09)
- [x] Baseline image built from source: `python scripts/target.py build` (2026-10-09, B workstation; needed the output-check gate and no `# syntax` fetch, see `infra/containers/README.md`)
- [x] `baseline_image_digest` recorded: local image ID `sha256:e106dde7…` (registry digest comes in B2)
- [x] Source-built baseline runs and `smoke` returns products for `q=apple` (ids 1, 24, 47; local, 2026-10-09)
- [x] Injection reproduced on the source-built baseline: `q=xyz` returns 0 products, `q=xyz')) OR 1=1--` returns 56
- [x] Confirmed only Juice Shop's bundled fictional seed data is in use (2026-10-09, source-built baseline): no volumes or env overrides on the container; the 23 listed users all come from upstream `data/static/users.yml` at the pinned commit (including its two maintainer addresses), plus our synthetic `@antibody.invalid` canaries; 46 products
- [x] A told the pin is ready (`18348ca`; acknowledged in [plan-for-A.md](../plan-for-A.md))
- [x] A told about upstream answer files `data/static/codefixes/unionSqlInjectionChallenge_*` (collab Q4; A excludes them from agent context, C's `src/server/answer_match.py` flags exact matches)
- [x] Keep both ids (B, 2026-10-09): `target_id` `juice-shop` is the identity (config file, image tag, `Run.target_id`); the fixture's `targetId` `juice-shop-v20.2.0` is a version label in the suite report only. Renaming it would change the suite hash

## Contract review with A (before B4/B5)

- [x] `CheckResult` gets `image_digest` and `suite_hash` (collab Q7; `src/contracts/models.py`, both optional)
- [x] `Observation.release_ref` becomes `str | None` (collab Q7)
- [ ] Release/check interfaces agreed with A and C. The runner (`src/server/runner.py`, C) already defines `DeployConnector.deploy(DeployRequest) -> DeployResult` and a `build_candidate(Candidate) -> image digest` callable; confirm these are B's interfaces.

## B2. Prove rebuilt-image public deployment (target: first ~40 min)

- [x] Build with a trivial harmless patch and push it to the registry: `spike-marker.patch` via `build-target`, image `ghcr.io/hackathon-corner/antibody-target@sha256:2b20151b193d5c9800892992f7e3f93d40c91811bd1602a8f6428ad8020668a8` ( [run 37983610899](https://github.com/hackathon-corner/antibody/actions/runs/37983610899))
- [x] Deployment definition: `infra/akash/juice-shop.sdl.template.yaml`, rendered for the spike digest to `runtime/akash/juice-shop-2b20151b193d.sdl.yaml` (2026-10-09)
- [ ] Deploy that digest to Akash (C's console, with GHCR credentials); record lease ID and URL
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
- [x] Re-run in baseline mode against the source-built baseline image (`sha256:e106dde7…`, fresh container, 2026-10-09): overall `pass`. Ordinary search matches all 6 queries; injection reproduced (canary leaked, 24 credential-shaped rows); access boundary 401/200; edge cases observed (quote → HTTP 500). Output in ignored `artifacts/b3/baseline-source-built.json`
- [x] Suite hash recorded: `check_suite.sha256` = `be833ec4…` in `config/targets/juice-shop.json`; `tests/unit/test_target_pins.py` fails if the suite or fixture changes without updating it
- [x] Definitions out of the agent's reach: the worker bind-mounts the suite and fixture read-only from the host checkout into a separate pinned Node container (`src/adapters/check_worker.py:227`); the candidate only changes `routes/search.ts` inside the image build
- [x] Q5 answered: keep `.mjs` (B, 2026-10-09)

## B4. Isolated candidate verification worker

- [x] Independent change-scope check: only `routes/search.ts`, rejected before build; also catches deletes, renames and binary patches (`src/adapters/check_worker.py`, unit-tested)
- [x] Builds the candidate with an allowlisted environment (no secrets), runs it on a per-check `--internal` Docker network with CPU, memory, pid limits and dropped capabilities; build and suite have timeouts. (The build itself needs network to fetch the pinned source and npm packages.)
- [x] Runs the B3 suite in candidate mode (suite mounted read-only from the host checkout); emits `CheckResult` tied to candidate hash, image ID and suite hash. Observed 2026-10-09 on an operator-supplied parameterized-query repair (not model output): all 5 required checks pass, image `sha256:02a8df7b…`, suite `2d7e0519…` (from the CRLF checkout, before the LF pin below; the same suite now hashes `be833ec4…`)
- [x] An error or unknown result blocks release: timeouts, unparseable output, suite-hash or mode mismatch, exit/overall disagreement and a target that never starts are `ERROR`; `build_candidate` refuses anything without a passing record (unit-tested)
- [x] Entry points match the runner's `build_candidate(Candidate) -> str` and A's `run_checks(Candidate) -> tuple[CheckResult, ...]` (`load_worker()`)
- [ ] A wires `load_worker().run_checks` into `RepairAgent`, and C passes `build_candidate` to `HostRunner.execute`
- [x] Negative control through the worker: the `WHERE 1=0` mutant is rejected. operator-supplied `tests/fixtures/juice-shop/candidates/mutant-where-1-0.patch` (origin `operator-supplied-bad-candidate`, candidate `37818c3f…`, image `sha256:412454ae…`, suite `be833ec4…`, 2026-10-09): `search.ordinary` fails (0 products for every query) while injection, edge cases and access boundary pass; `build_candidate` refused it
- [x] Suite hash no longer depends on line endings: `tests/e2e/**` and `tests/fixtures/**` pinned to `eol=lf` in `.gitattributes`. Windows now hashes the suite as `be833ec4…`, matching CI run 37983610899

## B5. Fixed deployment connector and external verification

Progress (2026-10-09, not yet run against real Akash, so nothing below is ticked): `src/adapters/akash_deploy.py` (`load_connector()`) implements the first three items. It re-checks the worker's verification record, pushes the verified image to GHCR as `cand-<hash12>`, deploys by registry digest via the Akash Console API with read-only pull credentials from the environment, serializes through one coordinator row in `runtime/deploy/akash.sqlite`, and `reconcile()` resolves unfinished attempts from Akash's state without redeploying. 17 unit tests in `tests/unit/test_akash_deploy.py`. Probes: `src/adapters/public_probe.py` (CLI `scripts/probe_public.py --mode baseline|candidate`), reached from the connector as `observe(attempt_id)`, emit one `Observation` per probe. Observed locally (2026-10-09, not yet against a public endpoint): the source-built baseline passes baseline mode and fails candidate mode (quote → 500, 26 credential-shaped injection rows); the operator-supplied repair image `sha256:02a8df7b…` passes candidate mode (injection 0 rows, quote 200, all 6 ordinary searches). 9 probe tests in `tests/unit/test_public_probe.py`.

- [ ] `DeployConnector.deploy(request)` for `src/server/runner.py`: candidate hash and image digest only; no arbitrary host, URL, command or `latest` tag
- [ ] Deployments serialized; durable state; reconciles with the host after a restart or timeout (the runner's `RunStore.claim_deploy` already records claims; the connector must reconcile with the host's actual state)
- [ ] Emits `DeployResult`; acceptance by the host is not treated as proof the image is serving
- [ ] External probes repeat the search and injection checks and emit `Observation`

## B6. Bad-candidate tests (with A)

- [x] Candidate that breaks search is rejected by the same gate: the `WHERE 1=0` mutant through `run_checks` + `build_candidate` (see B4)
- [x] Candidate that edits tests or forbidden paths is rejected before build: `tests/fixtures/juice-shop/candidates/forbidden-weakens-suite.patch` (the real repair plus a hunk that disables the suite's leak check; origin `operator-supplied-bad-candidate`, candidate `d0abb819…`, 2026-10-09) through the real worker: `worker.scope` FAIL naming `tests/e2e/juice-shop-checks.mjs`, no build, and `build_candidate` refused it (no verification record). A's agent-side validator rejects the same case in `tests/unit/test_adversarial_candidate.py`
- [x] A legitimate repair passes; each candidate's origin is labeled accurately: `candidates/repair-parameterized.patch` (origin `operator-supplied-reference-repair`, **not model output**; candidate `7fe1347b…`) passes all 5 required checks on the current suite `be833ec4…`, and `build_candidate` released image `sha256:4be6e636…` (2026-10-09). A model-produced repair still depends on A's Guild run

## B7. Stretch: stable alias and recovery

- [ ] Promote behind a stable alias, then recover to the previous revision, both tied to exact digests
- [ ] Restoring a vulnerable baseline is not described as a security fix
