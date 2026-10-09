# tests/fixtures/juice-shop

Owner: B.

Attributed pinned target metadata and synthetic test inputs. Target-specific behavior belongs here, not generic product modules.

Target: [OWASP Juice Shop](https://github.com/juice-shop/juice-shop) `v20.2.0` (`5658473cf8814459bf89000ce373b20ed0b4eb37`), MIT, Copyright (c) 2014-2026 Bjoern Kimminich & the OWASP Juice Shop contributors. Its vulnerabilities are intentional; we do not report them as new or submit fixes upstream.

Data: the target runs only on Juice Shop's bundled, fictional seed data (products, users) created at startup. No customer records.

Note for A: upstream ships answer files for this exact challenge under `data/static/codefixes/unionSqlInjectionChallenge_*`. If the agent sees or copies one, record that in the candidate's origin/guidance.

`candidates/`: operator-supplied bad candidates for the rejection demo and negative controls. Label their origin as `operator-supplied-bad-candidate`, never as model output. `mutant-where-1-0.patch` replaces the search query with `WHERE 1=0`: no injection, but search returns nothing. `forbidden-weakens-suite.patch` carries the real repair plus an edit that disables the suite's leak check; it must be rejected before build. `repair-parameterized.patch` is an operator-supplied reference repair (parameterized query), used to prove the pipeline end to end. Label it `operator-supplied-reference-repair`, never as the agent's repair. It must not be given to the agent as context.

Status: `search-expectations.json` recorded from the pinned baseline. See [the PRD](../../../docs/PRD.md).
