# API-10 / API-11: PRs #23 and #24 deployed and verified (2026-10-07)

Reply to `notes/api-10-api-11-merged-please-deploy-and-verify-20261007.md`.

From the ddp-api session (Claude Code, on the ddp-api host), at Ramon's request.

## Step 1: deploy + restart -- done

`main` fast-forwarded from `d89c7c4` to `da82158`. `ddp-api` restarted cleanly (key store loaded
7 keys). Dependencies untouched: still `fastapi 0.128.0`, `starlette 0.50.0`. Service unit has no
`--workers` flag, so the default of one worker applies.

## Step 2: verify -- no-key checks confirmed, on both `http://127.0.0.1:5000` and the public URL

Identical output from both:

```
swagger-ui-dist@5.33.1/swagger-ui.css
swagger-ui-dist@5.33.1/swagger-ui-bundle.js
plugins: [BlockWriteTryItOut]
write ops flagged: 30
GET flagged (0): 0
/admin paths (0): 0
admin schemas ([]): []
```

As expected, the flagged-write count is unchanged from the previous deploy (30).

## Not done

- The admin-key checks (`GET /admin/openapi.json` listing four paths, and `POST /admin/keys` with
  `EXAMPLE-DO-NOT-USE` returning 422): this session has no admin key. That 422 check, first requested
  for API-8, is still open.
- The browser walkthrough (Try it out present on GETs and `POST /votebot/chat`, absent on
  `POST /trigger/user-sync`).

Ramon decides whether to close API-10/API-11 on the evidence above or ask for those.

No dependency, config or secret changes. Rollback target, if ever needed: `d89c7c4`.
