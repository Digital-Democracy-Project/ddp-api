# INFRA-7 / Swagger "Try it out": PR #17 merged -- please deploy, restart and verify (2026-10-05)

From the dev agent, at Ramon's request. Checked directly: PR #17 (`fix(docs): Swagger Authorize hint + persist token (INFRA-7)`) is merged to `main` (merge commit `1a0464a`).

**What it does (docs page only, no change to any endpoint or to authentication):**
- the description at the top of `/docs` now says to click **Authorize** and paste a DDP API key, and that without one "Try it out" returns `401 Not authenticated`;
- Swagger remembers the pasted key across page reloads (`persistAuthorization`), on `/docs` and `/admin/docs`.

**Why:** "Try it out" has been returning 401 for everyone because 96 of the 99 operations in my local build require a bearer token and nothing on the page said so. The gateway is working as designed. A shared token on the page and an internal allowlist were deliberately not done (the request runs in the visitor's browser, and a public token would work for anyone).

## Step 1: get `1a0464a` onto the host and restart

The page text and the Swagger settings are built when the process starts, so a restart is needed after the code is in place. Use your usual path for ddp-api:

```bash
sudo systemctl restart ddp-api
sudo systemctl status ddp-api
```

## Step 2: verify

The page itself, no key needed:

```bash
curl -s https://api.digitaldemocracyproject.org/docs | grep -o '"persistAuthorization": true'
curl -s https://api.digitaldemocracyproject.org/openapi.json | python3 -c "import json,sys; s=json.load(sys.stdin); print(s['components']['securitySchemes']); print(s['info']['description'][:200])"
```

Expect `"persistAuthorization": true`, an `HTTPBearer` scheme, and a description that starts with the Authorize instructions.

Then the real check from INFRA-7: with a real DDP API key, a request that does what "Try it out" will do must return 200:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://api.digitaldemocracyproject.org/broker/jurisdictions \
  -H "Authorization: Bearer $DDP_API_READ_TOKEN"
```

If you can, also open `/docs` in a browser, click **Authorize**, paste the key, and run "Try it out" on `/broker/jurisdictions`; that is the exact path the ticket describes, and I could not exercise it from here.

## Report back

Restart confirmed, the three outputs above (the `persistAuthorization` line, the scheme and description, and the status code). Please do not paste a key. If the curl with a real key does not return 200, say what it returned; that is a real gap to report, not something to route around. Ramon closes the INFRA-7 follow-up from your report (the ticket itself is already Done on the strength of the code review).

Reply on this branch either way.
