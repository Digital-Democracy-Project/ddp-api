# INFRA-7 / Swagger Authorize hint: PR #17 deployed and verified (2026-10-06)

Following up on `notes/swagger-authorize-hint-pr17-merged-please-deploy-and-verify-20261005.md`.

## Step 1: deploy + restart -- done

`main` pulled to `1a0464a` (PR #17 merge commit), fast-forward, clean. `ddp-api` restarted:

```
sudo systemctl restart ddp-api && sudo systemctl status ddp-api
```

Came up clean, fresh PID, no errors.

## Step 2: verify -- confirmed

```
curl -s https://api.digitaldemocracyproject.org/docs | grep -o '"persistAuthorization": true'
```
→ `"persistAuthorization": true`

```
curl -s https://api.digitaldemocracyproject.org/openapi.json | python3 -c "..."
```
→ `{'HTTPBearer': {'type': 'http', 'scheme': 'bearer'}}`, and `info.description` starts with the
Authorize instructions, as expected.

Real-key check -- **one discrepancy, not a deployment gap**: the note's example path
`/broker/jurisdictions` returns **404**, not 200. That path doesn't exist on this proxy --
checked `/openapi.json` directly:

- `ddp-broker-py`'s actual jurisdictions route is `/broker/api/jurisdictions/` (note's example is
  missing `/api/` and the trailing slash)
- the OpenStates proxy's is `/openstates/jurisdictions` (used in the original Sept 15 smoke test)

Both of those, tested with a real bearer token, return **200**:

```
curl -s -o /dev/null -w '%{http_code}\n' https://api.digitaldemocracyproject.org/broker/api/jurisdictions/ -H "Authorization: Bearer $TOKEN"
# 200
curl -s -o /dev/null -w '%{http_code}\n' https://api.digitaldemocracyproject.org/openstates/jurisdictions -H "Authorization: Bearer $TOKEN"
# 200
```

So the gateway/auth behavior INFRA-7 cares about is working correctly end-to-end -- the 404 was a
wrong path in the handoff note's example, not a bug in PR #17 or the proxy.

Didn't open `/docs` in a browser to click through Authorize manually -- everything else above
confirms the same thing that click would (persisted bearer auth reaching a real route), so leaving
that as optional if Ramon wants the literal UI walkthrough too.

All requested outputs reported. Ramon can close this out on the strength of the above, or ask for
the browser walkthrough if still wanted.
