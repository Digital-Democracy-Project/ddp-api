# VOTEBOT-2 / OpenStates proxy: PR #15 merged -- please restart, verify, and mint VoteBot's key

Checked directly: PR #15 (`fix(openstates-proxy): make the internal api-v3 key configurable via
env`) is merged to `main` (merge commit `d1cab0f`). It makes `OPENSTATES_PROXY_KEY` an env var,
same pattern as the existing `OPENSTATES_SERVICE_URL`, default unchanged so nothing breaks for
environments that don't set it.

Background: production migrated its OpenStates data source off the Mac Studio-hosted Postgres
onto a Fargate/EC2/RDS-backed api-v3 at `http://10.0.0.11:8002`. This proxy's own
`OPENSTATES_SERVICE_URL` had never been updated to match -- it was still defaulting to the old
Mac Studio address (`10.0.0.8:8002`), and the internal `x-api-key` it forwards to api-v3
(`_OPENSTATES_INTERNAL_KEY`) was hardcoded in source with no env override at all, so there was no
way to point it at the new instance's own registered key even if the URL was fixed. Ramon has
already found the real key and put both values in the real `ddp-api/.env`
(`OPENSTATES_SERVICE_URL=http://10.0.0.11:8002` and the real key under `OPENSTATES_PROXY_KEY`).

## Step 1: restart -- the .env edit alone has done nothing yet

Both `OPENSTATES_SERVICE_URL` and `OPENSTATES_PROXY_KEY` are read once, at process import time
(`app/routes/openstates_proxy.py`). Editing `.env` does not take effect until the process
restarts:

```bash
sudo systemctl restart ddp-api
sudo systemctl status ddp-api
```

## Step 2: real smoke test, not just "no crash"

```bash
curl -s https://api.digitaldemocracyproject.org/openstates/jurisdictions \
  -H "Authorization: Bearer $DDP_API_READ_TOKEN"
```

A `200` with real jurisdiction data confirms the URL and key are both correct together. A `401`
means the key in `.env` isn't actually registered in `10.0.0.11`'s own `profiles_profile` table
yet (api-v3 validates it against that instance's database, not against anything in this repo) --
if you get that, it's a real gap to report back, not something to route around here.

## Step 3: mint VoteBot's own read key

Separate from all of the above -- VoteBot needs its own `ddp-api` bearer token to call
`/openstates/*` at all (this is a completely different key from Step 2's internal one; VoteBot
never sees that one). None exists yet. Please issue one, scoped read-only and restricted to just
this route so a leak of it can't reach anything else:

```bash
curl -s -X POST https://api.digitaldemocracyproject.org/admin/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "VoteBot OpenStates replica", "scopes": ["read"], "restrictions": {"endpoints": ["/openstates"]}}'
```

The response shows the plaintext key exactly once. That value goes into VoteBot's own
`.env` as `DDP_OPENSTATES_BEARER_TOKEN` -- please hand it back rather than setting it there
directly, since that's a separate host/repo (`votebot`, PR #6, already merged and waiting on
exactly this key before `USE_DDP_OPENSTATES_REPLICA` can be flipped on).

Report back: restart confirmed, Step 2's actual response (200 or 401 and which), and the new
key's `name`/id (not the plaintext, over whatever channel you send it back on).
