# API-8 / API-10 / API-11: admin-key checks passed (2026-10-07)

Follow-up to `notes/api-10-api-11-deployed-and-verified-20261007.md`, which left the admin-key
checks open.

From the ddp-api session (Claude Code, on the ddp-api host), at Ramon's request.

## Result: both checks pass, against the public URL (`https://api.digitaldemocracyproject.org`)

- **Admin spec.** `GET /admin/openapi.json` lists exactly
  `['/admin/keys', '/admin/keys/{key_id}', '/admin/keys/{key_id}/rotate', '/admin/reload']`.
  Confirms the API-11 admin filter on the deployed build (`da82158`, `fastapi 0.128.0`).
- **Reserved name.** `POST /admin/keys` with the name `EXAMPLE-DO-NOT-USE` (read scope, already
  expired) returned **422**. No key was created. Confirms API-8 is running; this was open since
  the `d89c7c4` deploy.

## Caveat

The credential used was the env-var fallback `API_BEARER_TOKEN` from the host's `.env`, which
carries full admin scope. It was not printed or pasted anywhere. A managed `ddp-admin-` key was
not used; the endpoints behave the same for either, but this does not exercise the managed-key
path. The README says to retire the env-var token once managed keys are in use.

## Still open

The optional browser walkthrough of `/docs`: Try it out should be present on GET operations and
`POST /votebot/chat`, and absent on `POST /trigger/user-sync`. Not done by any session so far.

Ramon decides whether to close API-8, API-10 and API-11 on the evidence in these notes or ask for
the walkthrough first. Nothing further requested from ops.
