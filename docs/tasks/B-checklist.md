# Builder B checklist: target, independent verification, deployment

Owner: B. Task IDs and "done when" criteria come from [PRD §8](../PRD.md#builder-b--target-independent-checks-and-deployment). Tick a box only when its result has actually been observed. Put evidence (digest, URL, run ID) next to the item.

Stack: Python 3.11+ (stdlib first) for B's code, Docker for target builds. Juice Shop stays Node inside its container.

## 0. Workstation and access

- [x] Python 3.11+ installed (3.12.10 via winget, 2026-10-09). Open a new shell so it's on PATH.
- [x] Docker Desktop installed and running (engine 29.8.1 on WSL2, verified 2026-10-09)
- [ ] Public host chosen: Akash or a fallback we're authorized to use
- [ ] Container registry access (push/pull) for candidate images
- [ ] Team fork of Juice Shop created under the org; `source.repo` in `config/targets/juice-shop.json` updated, commit unchanged

## B1. Pin source/image, start target, synthetic baseline data

- [x] Upstream commit pinned: `v20.2.0` / `5658473cf8814459bf89000ce373b20ed0b4eb37` ([decision 0001](../decisions/0001-target-pin.md))
- [x] Base images pinned by digest (git, `node:24`, distroless `nodejs24-debian13`)
- [x] Target config written: `config/targets/juice-shop.json`
- [x] Dockerfile written: `infra/containers/juice-shop/Dockerfile`
- [x] Target script written: `scripts/target.py` (source / build / run / smoke / stop)
- [ ] `python scripts/target.py source --out runtime/source` runs; `routes/search.ts` hash matches the one in `config/targets/README.md`
- [ ] Baseline build succeeds: `python scripts/target.py build`
- [ ] `baseline_image_digest` recorded in `config/targets/juice-shop.json`
- [ ] Baseline runs locally and `smoke` returns products for `q=apple`
- [ ] Confirmed only Juice Shop's bundled fictional seed data is in use
- [ ] Commit pushed; A told the pin is ready (A is blocked on this)
- [ ] A told about upstream answer files `data/static/codefixes/unionSqlInjectionChallenge_*`

## Contract review with A (before B4/B5)

- [ ] `CheckResult` gets `image_digest` and `suite_hash` (PRD §5 requires binding to them)
- [ ] `Observation.release_ref` becomes `str | None` (PRD §6: "where observed")
- [ ] Release/check interfaces agreed with A and C

## B2. Prove rebuilt-image public deployment (target: first ~40 min)

- [ ] Build with a trivial harmless patch, push it to the registry, record its registry digest
- [ ] Deploy that digest to the public host; definition goes in `infra/akash/` or `infra/containers/`
- [ ] External HTTP fetch, from outside this machine, shows the rebuilt image serving search
- [ ] If Juice Shop can't be rebuilt promptly: escalate per PRD §9 (smaller attributed target, disclosed)

## B3. Baseline exploit and functionality checks (before A's first candidate)

- [ ] Suite in `tests/e2e/` (Python): ordinary search returns expected product IDs and response shape
- [ ] Edge cases: empty `q`, quotes and punctuation, the 200-char limit
- [ ] Injection probe reproduces the baseline effect using a synthetic canary; no raw rows published
- [ ] One protected endpoint: unauthenticated denial and authenticated behavior recorded
- [ ] Expected results recorded from the pinned baseline in `tests/fixtures/juice-shop/`
- [ ] Suite hash computed and recorded; definitions out of the agent's reach

## B4. Isolated candidate verification worker

- [ ] Independent change-scope check: only `routes/search.ts`, rejected before build
- [ ] Builds the candidate with no secrets and restricted network, with bounded CPU, memory and time
- [ ] Runs the B3 suite; emits `CheckResult` tied to candidate hash, image digest and suite hash
- [ ] An error or unknown result blocks release

## B5. Fixed deployment connector and external verification

- [ ] `deploy(candidate_hash, image_digest)` only; no arbitrary host, URL, command or `latest` tag
- [ ] Deployments serialized; state kept in a durable local store; reconciles with the host after a restart or timeout
- [ ] Emits `DeployResult`; acceptance by the host is not treated as proof the image is serving
- [ ] External probes repeat the search and injection checks and emit `Observation`

## B6. Bad-candidate tests (with A)

- [ ] Candidate that breaks search is rejected by the same gate
- [ ] Candidate that edits tests or forbidden paths is rejected before build
- [ ] A legitimate repair passes; each candidate's origin is labeled accurately

## B7. Stretch: stable alias and recovery

- [ ] Promote behind a stable alias, then recover to the previous revision, both tied to exact digests
- [ ] Restoring a vulnerable baseline is not described as a security fix
