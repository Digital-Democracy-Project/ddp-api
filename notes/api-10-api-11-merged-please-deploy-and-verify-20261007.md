# API-10 / API-11: PRs #23 and #24 merged -- please deploy, restart and verify (2026-10-07)

Follow-up to `notes/api-11-api-10-answers-fastapi-pin-admin-filter-swagger-pin-20261007.md`.

From the dev agent (Claude Code, ddp-api repo), at Ramon's request. Checked directly: PRs #23 and #24 are merged to `main`; `main` is now `da82158` (merge of #24). I ran the full suite on that commit under both FastAPI 0.141.1 and a venv with `fastapi 0.128.0` / `starlette 0.50.0` (this host's versions): 185 passed, 15 failed on both, and the 15 are all in `tests/test_webflow.py` (`webflow_cms` is not installed in my venv). I also ran every command below against the merged code on 0.128.0.

## What changed

- **#23 (API-11):** the public and admin OpenAPI documents are now cut by their built paths instead of route objects. On this host's FastAPI 0.128.0 both documents are byte-identical to before, so **expect no visible change**. `requirements.txt` now says `fastapi>=0.128.0,<0.142.0`.
- **#24 (API-10):** the public `/docs` page loads Swagger UI from `swagger-ui-dist@5.33.1` (script and stylesheet) instead of the floating `@5`. This is the only visible change; the host's browsers need to reach `cdn.jsdelivr.net`, as before.

No new environment variables, secrets or config.

## Step 1: get `da82158` onto the host and restart

```bash
git pull   # on main; expect da82158
sudo systemctl restart ddp-api
sudo systemctl status ddp-api
```

Keep `--workers 1`. **Do not reinstall or upgrade Python dependencies for this**; the installed `fastapi 0.128.0` already satisfies the new range.

## Step 2: verify

Checked against `http://127.0.0.1:5000` or the public URL, no key needed:

```bash
BASE=https://api.digitaldemocracyproject.org   # or http://127.0.0.1:5000

curl -s $BASE/docs | grep -o 'swagger-ui-dist@[^/]*/[a-z.-]*\|plugins: \[BlockWriteTryItOut\]'

curl -s $BASE/openapi.json | python3 -c "
import json,sys
s=json.load(sys.stdin)
ops=[(m,p,o) for p,i in s['paths'].items() for m,o in i.items() if isinstance(o,dict)]
print('write ops flagged x-ddp-write:', sum(1 for m,p,o in ops if o.get('x-ddp-write')))
print('GET ops flagged (expect 0):', sum(1 for m,p,o in ops if m=='get' and o.get('x-ddp-write')))
print('/admin paths in public spec (expect 0):', sum(1 for p in s['paths'] if p.startswith('/admin')))
print('admin-only schemas in public spec (expect []):', [n for n in s['components']['schemas'] if n in ('IssueKeyRequest','IssueKeyResponse','ListKeysResponse','RevokeKeyResponse','RotateKeyRequest','RotateKeyResponse')])
"
```

Expect exactly three lines from the first command: `swagger-ui-dist@5.33.1/swagger-ui.css`, `swagger-ui-dist@5.33.1/swagger-ui-bundle.js` and `plugins: [BlockWriteTryItOut]`. For the second, `GET ops flagged` is 0, `/admin paths` is **0**, and the schema list is `[]`. The flagged-write count depends on which downstream services are reachable (41 on my dev box, 30 on this host earlier), so do not compare it to a number; just report it. If `/admin paths` is not 0, stop and report, do not route around it.

Then, with an **admin** key (do not paste it). This covers both the new admin-document check and the `POST /admin/keys` check left open from the last report:

```bash
curl -s $BASE/admin/openapi.json -H "Authorization: Bearer $DDP_ADMIN_KEY" \
  | python3 -c "import json,sys; print(sorted(json.load(sys.stdin)['paths']))"

curl -s -o /dev/null -w '%{http_code}\n' -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $DDP_ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"EXAMPLE-DO-NOT-USE","scopes":["read"],"expires_at":"2000-01-01T00:00:00Z"}'
```

Expect `['/admin/keys', '/admin/keys/{key_id}', '/admin/keys/{key_id}/rotate', '/admin/reload']` and then **422**. If the second returns 200, the API-8 code is not running: revoke the key it created (find it by that name in `GET /admin/keys`) and report that. The request is built to be harmless either way (a read-only key that is already expired).

Optional, in a browser: open `/docs`, expand a few operations. `GET` operations and `POST /votebot/chat` should have a **Try it out** button; `POST /trigger/user-sync` should have none. I verified this against a local server on the pinned version, not against production.

## Rollback

Previous `main`: `d89c7c4` (the #22 merge).

## Report back

Restart confirmed, the printed output of the commands above, and the status code from the admin check. Please do not paste a key. If anything differs from the expectations, say what you saw; that is a real finding, not something to work around. Ramon moves API-10 and API-11 to Done from your report.

Reply on this branch either way.
