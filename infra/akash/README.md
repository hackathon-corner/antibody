# infra/akash

Owner: B.

Authorized Akash deployment definitions and setup notes. No credentials.

- `juice-shop.sdl.template.yaml`: one Juice Shop service, port 3000 exposed globally as 80, 1 CPU, 2 GiB memory, 4 GiB storage. The image is a placeholder; render it with `scripts/render_akash_sdl.py --image ghcr.io/hackathon-corner/antibody-target@sha256:<digest>`, which refuses tags and writes to the ignored `runtime/akash/`.
- `scripts/probe_public.py --url <lease URL> --expect-name <name>`: external probe. It checks that the endpoint reports the application name of our rebuilt image and that `q=apple` returns the B3 fixture's products. It prints `Observation` records.

## B2 runbook (prove a rebuilt image is publicly served)

1. Image: the `build-target` workflow's `spike-marker.patch` image, by digest from its build record (`image` field). The marker sets the app name to `OWASP Juice Shop (Antibody build spike)`, so upstream's own image can't pass the probe.
2. Pull access: the GHCR package is private. Either give the lease read-only registry credentials, or make the package public. See Q6 in [collab.md](../../docs/collab.md).
3. Render the SDL for that digest and create the deployment from C's Akash Console account (C created it; don't create a second one). Accept a bid and note the lease URL.
4. From outside the lease: `python scripts/probe_public.py --url <lease URL> --expect-name "OWASP Juice Shop (Antibody build spike)" --release-ref <digest>`. Record the output, lease ID and URL in [the B checklist](../../docs/tasks/B-checklist.md).
5. Close the lease when it's no longer needed. Juice Shop is deliberately vulnerable.

Status: SDL template, renderer and probe written and tested locally (probe against the local baseline, renderer against tag/digest input). Nothing deployed yet. See [the PRD](../../docs/PRD.md).

## Files

- `evidence-api.yaml` (owner: C): evidence API + dashboard. Secrets are `<...>` placeholders filled in the Akash console only.
- Juice Shop target SDL (owner: B, B2): not yet written.
