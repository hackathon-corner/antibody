# tests/fixtures/juice-shop

Owner: B.

Attributed pinned target metadata and synthetic test inputs. Target-specific behavior belongs here, not generic product modules.

Target: [OWASP Juice Shop](https://github.com/juice-shop/juice-shop) `v20.2.0` (`5658473cf8814459bf89000ce373b20ed0b4eb37`), MIT, Copyright (c) 2014-2026 Bjoern Kimminich & the OWASP Juice Shop contributors. Its vulnerabilities are intentional; we do not report them as new or submit fixes upstream.

Data: the target runs only on Juice Shop's bundled, fictional seed data (products, users) created at startup. No customer records.

Note for A: upstream ships answer files for this exact challenge under `data/static/codefixes/unionSqlInjectionChallenge_*`. If the agent sees or copies one, record that in the candidate's origin/guidance.

Status: Expected-result fixtures pending B3 (needs a running baseline). See [the PRD](../../../docs/PRD.md).
