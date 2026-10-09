> **Where this comes from.** API-12 (https://digitaldemocracyproject.atlassian.net/browse/API-12) is about **this repo's public `/docs` page**; the fix had to go in ddp-broker-py (PR #422, merged), because ddp-api merges the broker's schema. **ddp-api itself needs no deploy and no change.** The same request is on ddp-broker-py's `notes/ops-handoff` branch; this copy is here so you see it on the ddp-api branch you already watch. Reply on **either** branch, and say which.

# Request (2026-10-09): deploy `b65a1b1c` -> `28fdb2f5` (API-12: six views declare their query parameters), then confirm on the public /docs page

PR #422 is merged. It is **documentation of the API only**: no behaviour change, no migration, no requirements, Dockerfile, compose, nginx or env change. Deploy it when it suits you; it does not depend on, and does not block, the held steps (slug backfill, search switches, keys, workers, resize). If one of those is mid-flight, finish it first and do this after.

## Why
ddp-api's public Swagger page (`https://api.digitaldemocracyproject.org/docs`) merges this broker's OpenAPI schema. Six GET views read `request.query_params` without declaring them, so their `?q=&type=...` appeared only in the description and "Try it out" had no fields to fill in (ticket API-12). The change adds `@extend_schema(parameters=...)` to those views. Nothing about request handling changes.

## What is in it (exactly three commits on top of `b65a1b1c`)
`git diff --name-only b65a1b1c 28fdb2f5` is exactly: `ddpbroker/views/search_api.py`, `bill_artifacts_api.py`, `bill_organization_positions_api.py`, `concept_statements_api.py`, one new test file `ddpbroker/tests/test_schema_query_params.py`, and `notes/primitives.md`. **Zero migrations.**

**`28fdb2f54903a50af3a0bbd5d7285b8a1008682b` is `origin/main` as of 2026-10-09 ~20:10 UTC. If `origin/main` has moved, STOP and tell me:** anything newer has not been looked at.

## Steps (you run everything on the host)
Use the real compose command from the 10-08 corrections (`docker compose -p ddp-broker-py --env-file /opt/ddp-broker-py/.env -f /opt/ddp-broker-py/infra/compose/prod.yml ...`) and **`--no-build`** wherever it recreates `web`.

1. Pre-flight: `/opt/ddp-broker-py` clean on `main`; `git rev-parse --short HEAD` expects `b65a1b1c` (if it already says `28fdb2f5`, skip to step 3 and say so); `git fetch origin main`; `git rev-parse origin/main` expects the full hash above.
2. `git pull --ff-only`, then **recreate `web` only** (`up -d --no-deps --no-build web`). The views are served by `web`; **`celery` and `celery-beat` do not need a restart** (no task code changed), so the tally-task caution from the 10-08 corrections does not apply. Confirm `web` reads `healthy` and `https://.../api/status/` answers 200.
3. Confirm the broker's own schema (read-only, from the host, no credential needed): `curl -s -H 'Accept: application/vnd.oai.openapi+json' http://localhost:8080/api/schema/ | python3 -c "import json,sys; p=json.load(sys.stdin)['paths']; print({k:[x['name'] for x in p[k]['get'].get('parameters',[])] for k in ['/api/search/','/api/search/suggest/','/api/bill-artifacts/status/','/api/bill-organization-positions/current/','/api/bill-organization-positions/status/','/api/concept-statements/status/']})"` (adjust the port if `web` is not on 8080 on the host). **Expect:** `search` -> `q, type, jurisdiction, session, page, per_page`; `suggest` -> `q`; `bill-artifacts/status` -> `jurisdiction, session, gov_id, versions`; `bill-organization-positions/current` and `concept-statements/status` -> `jurisdiction, session, gov_id`; `bill-organization-positions/status` -> `bill_openstates_id`. Each was `[]` before.
4. Wait **5 minutes** (ddp-api caches the downstream spec for 300 s), then check what the public page now serves: `curl -s https://api.digitaldemocracyproject.org/openapi.json` and look at `/broker/api/search/` -> `get` -> `parameters` (same six names). ddp-api runs on a different host and needs **no deploy**; if the list is still empty after 10 minutes, tell me and do not restart anything.

## Please report
- The step-2 result (the commit now running, `web` healthy, status 200) and the step-3 and step-4 outputs.
- Whether anything unexpected showed in the `web` log in the first few minutes (a schema generation error would show once, when `/api/schema/` is first requested).

**Rollback:** `git checkout b65a1b1c` on the host and recreate `web`. Nothing persistent changed, so nothing else needs undoing.

Note for later (nothing to do now): `/api/search/` is limited in nginx to the ddp-api and WireGuard source ranges (#421). The public /docs page reaches it through ddp-api, so "Try it out" on a search route works without a change there.
