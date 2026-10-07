# API-7 / API-8 / API-9: PRs #18-#22 merged -- please deploy, restart and verify (2026-10-07)

From the dev agent (Claude Code, ddp-api repo), at Ramon's request. Checked directly: PRs #20, #21 and #22 are merged to `main`; `main` is now `d89c7c4` (merge of #22). I ran the full suite on that commit in a clean worktree: 174 passed, 16 failed, and the 16 are the same ones that fail on the previous `main` (15 in `tests/test_webflow.py` because `webflow_cms` is not installed in my venv, plus `test_admin.py::test_public_docs_hide_admin_routes`). None of the 16 is new.

**Not deployed yet, as far as I can tell:** when I fetched the live `/openapi.json` earlier today, `POST /sync/unified/all` still had `dry_run` defaulting to `false`, which means PRs #18 and #19 (merged earlier today, `3075854`) never reached the host either. Deploying `d89c7c4` ships all of #18 through #22 together.

## What changed

Docs page and one admin-validation change. No change to routing, scopes, key issuance or any proxied request.

- **#18, #19, #20 (API-7):** the request-body examples on `/docs` are non-destructive: `dry_run: true` where a route has one, inert placeholder values elsewhere. `POST /sync/unified/all` and `POST /trigger/legislator-bio-sync` default `dry_run` to true. Seven zero-input job routes carry a visible "starts a real job" warning.
- **#21 (API-8):** `POST /admin/keys` now refuses the name `EXAMPLE-DO-NOT-USE` with a 422 and saves nothing. **This is the only behaviour change to a real endpoint.** Any other name behaves as before.
- **#22 (API-9):** on the public `/docs` page, "Try it out" is turned off for write actions (every POST/PUT/PATCH/DELETE except 8 read-scoped POSTs). The API itself is unchanged; anyone with a key can still call any route directly. `/admin/docs` is unchanged.

No new environment variables, secrets, config or dependencies.

## Step 1: get `d89c7c4` onto the host and restart

The page, the spec and the examples are built when the process starts, so a restart is needed.

```bash
git pull   # on main; expect d89c7c4
sudo systemctl restart ddp-api
sudo systemctl status ddp-api
```

Two cautions:
- Run with a **single** worker, as before (`--workers 1`); the key store depends on it.
- **Do not reinstall or upgrade Python dependencies as part of this.** `requirements.txt` has `fastapi>=0.109.0` unpinned, and with FastAPI 0.141.1 (what I have locally) `/admin/*` routes show up on the public `/docs` because `public_openapi()` can no longer filter them by path. Production does not do this today (the live spec had no `/admin` paths this morning), so keep whatever FastAPI version is installed there. The check below confirms it.

## Step 2: verify

No key needed:

```bash
BASE=https://api.digitaldemocracyproject.org

# docs page carries the plugin and the existing token setting
curl -s $BASE/docs | grep -o 'plugins: \[BlockWriteTryItOut\]\|"persistAuthorization": true'

# spec: counts, admin absent, defaults flipped
curl -s $BASE/openapi.json | python3 -c "
import json,sys
s=json.load(sys.stdin)
ops=[(m,p,o) for p,i in s['paths'].items() for m,o in i.items() if isinstance(o,dict)]
print('write ops flagged x-ddp-write:', sum(1 for m,p,o in ops if o.get('x-ddp-write')))
print('GET ops flagged (expect 0):', sum(1 for m,p,o in ops if m=='get' and o.get('x-ddp-write')))
print('/admin paths in public spec (expect 0):', sum(1 for p in s['paths'] if p.startswith('/admin')))
def dflt(path,name):
    for prm in s['paths'].get(path,{}).get('post',{}).get('parameters',[]):
        if prm['name']==name: return prm.get('schema',{}).get('default')
print('/sync/unified/all dry_run default (expect True):', dflt('/sync/unified/all','dry_run'))
print('/trigger/legislator-bio-sync dry_run default (expect True):', dflt('/trigger/legislator-bio-sync','dry_run'))
print('read POSTs unflagged (expect True x4):', [not s['paths'][p]['post'].get('x-ddp-write') for p in ('/get_tokens','/get_users','/votebot/chat','/webflow/check/duplicates')])
"
```

Expect both grep lines; an `/admin` count of **0** (if it is not 0, stop and report, do not route around it); the two `dry_run` defaults `True` (the second only appears if ddp-sync's `main` routes are reachable through the proxy; if the path is absent, say so rather than treating it as a failure); and four `True`s.

Then the one real-behaviour check, with an **admin** key. The request is built to be harmless even if the deploy did not take: a read-only key that is already expired.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $DDP_ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"EXAMPLE-DO-NOT-USE","scopes":["read"],"expires_at":"2000-01-01T00:00:00Z"}'
```

Expect **422**. If it returns 200, the new code is not running: revoke the key it just created (`DELETE /admin/keys/{id}`, find it by that name in `GET /admin/keys`) and report that.

Optional, in a browser: open `/docs`, expand a few operations. `GET` operations and `POST /votebot/chat` should still have a **Try it out** button; a write route such as `POST /trigger/user-sync` or `POST /webflow/fill/gov-url` should have none. The plugin is browser-side and loads `swagger-ui-dist@5` from `cdn.jsdelivr.net`, so the browser must be able to reach it. I verified this against a local server but not against production.

## Rollback

Previous `main`: `3075854` (the #19 merge). The change is docs and one validation rule, so a rollback only needs a checkout and a restart.

## Report back

Restart confirmed, the printed output of the two verification blocks, and the status code from the admin check. Please do not paste a key. If anything differs from the expectations above, say what you saw; that is a real finding, not something to work around. Ramon moves API-7/8/9 to Done from your report.

Reply on this branch either way.
