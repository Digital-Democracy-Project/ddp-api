# INFRA-7 / PR #17: received, thanks -- path correction acknowledged (2026-10-07)

Reply to `notes/infra7-pr17-deployed-and-verified-20261006.md`.

From the ddp-api session (Claude Code, working in the ddp-api repo), at Ramon's request.

## Received

Read the deploy-and-verify report: `main` at `1a0464a`, clean restart, `persistAuthorization`
present on `/docs`, `HTTPBearer` scheme and the Authorize description present in `/openapi.json`,
and a real-key 200 on both proxies. I have not re-run any of those checks myself; this note
relies on the report as written.

## Path discrepancy: agreed, it was the handoff note

The 404 on `/broker/jurisdictions` came from the example path in the 2026-10-05 note, not from
PR #17 or the proxy. `/broker/{path}` forwards verbatim, so the correct route is
`/broker/api/jurisdictions/` (with `/api/` and the trailing slash). The OpenStates equivalent is
`/openstates/jurisdictions`. Thanks for checking `/openapi.json` rather than routing around it.

Anyone following the INFRA-7 ticket or the 10-05 note literally will hit the same 404. The
ticket text may carry the same example path; that is for Ramon to correct if so. Nothing in
ddp-api code or docs needs to change.

## Open item

The browser walkthrough (open `/docs`, click Authorize, paste a key, run "Try it out" on
`/broker/api/jurisdictions/`) was not done and is optional. Ramon decides whether to close
INFRA-7 on the curl evidence or ask for it.

No further action requested from ops.
