# Reply: FastAPI pin, admin filter, and a Swagger UI pin -- PRs #23 and #24 open, not merged (2026-10-07)

Reply to `notes/api-7-8-9-deployed-and-fastapi-pin-admin-filter-question-20261007.md`.

From the dev agent (Claude Code, ddp-api repo), at Ramon's request. Thanks for the deploy report and
for noting the exact versions (`fastapi 0.128.0`, `starlette 0.50.0`): I built a venv with those
two versions and ran the whole suite on it as well as on my own FastAPI 0.141.1, which is how the
answers below were checked.

**Nothing is merged and nothing is requested from ops yet.** Ramon merges; I will leave a
deploy-and-verify note here after that.

## Answers

1. **Pin.** `fastapi>=0.128.0,<0.142.0` (PR #23), not `==0.128.0`. Dev runs 0.141.1 and production
   0.128.0, the suite passes on both, and an exact pin would make one of them wrong. The ceiling is
   the part that matters: it stops an untested release being picked up silently. Starlette is left to
   FastAPI's own constraint (dev runs 1.6.0, production 0.50.0, suite green on both). The floor moved
   from 0.109.0 only because 0.128.0 is the oldest version actually tested. **Do not change what is
   installed on the host for this**; the pin only affects the next fresh install.
2. **What changed in 0.141.1.** Observed directly, not from the changelog (so I cannot say which release
   between 0.128 and 0.141 introduced it): routers added with `include_router` appear in `app.routes`
   as wrapper objects with no `path` attribute. `getattr(r, "path", "")` returns `""`, so the public filter
   kept every one of them (admin routes leaked), and the admin filter matched only the two docs routes
   (so `/admin/openapi.json` had **zero** paths, which means `/admin/docs` was empty on 0.141.1 too).
   On 0.128.0 routes are plain objects with `path`, which is why production was fine. Fix in #23:
   build both documents from all routes, then keep or drop by the **built spec's paths**, and drop component
   schemas no remaining path uses (otherwise `IssueKeyRequest` and friends would appear in the public
   document). It holds on both versions.
3. **Test.** Yes: `test_public_docs_hide_admin_routes` passes again, so the known failures go from 16
   to 15 (all `test_webflow.py`, `webflow_cms` not installed), identical on both versions. I also found
   and fixed one of my own tests (API-9's read-only-list check) that only understood 0.141's layout and
   failed on 0.128.0.
4. **Who and how.** The ddp-api session opened them. Two PRs, one per ticket:
   - **#23 (API-11):** the filter plus the pin together, since the pin range is justified by the filter
     being tested on both versions.
   - **#24 (API-10):** pins the Swagger UI script/stylesheet on the public `/docs` page to
     `swagger-ui-dist@5.33.1` instead of the floating `@5`.

## What deploying them will and will not change on this host

- **#23:** on 0.128.0 the public and admin documents are byte-identical before and after (I diffed
  them). Expect no visible change.
- **#24:** the only visible change is the two CDN URLs on `/docs` (`...swagger-ui-dist@5.33.1/...`).
  The host's browsers need to reach `cdn.jsdelivr.net`, as before.

## Still open from your last report

The admin-key `POST /admin/keys` check for `EXAMPLE-DO-NOT-USE` (expect 422) and the browser
walkthrough were not done. Neither is blocking; Ramon decides whether to ask for them.

Reply on this branch if anything above does not match what you see on the host.
