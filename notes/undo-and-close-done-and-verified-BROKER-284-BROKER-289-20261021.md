> **Reply to** `request-undo-sign-in-rules-and-close-public-admin-BROKER-284-BROKER-289-20261020.md` (BROKER-284, BROKER-289). Follows my pre-flight note `preflight-ok-undo-and-close-not-yet-run-BROKER-284-BROKER-289-20261021.md`. Replying on **this** branch (ddp-api `notes/ops-handoff`). No key, secret or public IP address is in this note.

# Done (2026-10-21, about 00:46 UTC): the BROKER-284 rules are removed and `/admin` and `/static` are closed on the public dev address; all checks as expected

Run on the host (`ip-172-31-81-51`), in the order of the request. Both scripts were the ones on this branch (the 284 copy `cmp`-identical, the 289 copy fetched from `origin/notes/ops-handoff`, 59 lines), and I read both before running. Each ran once; each exited 0. I did not try a sign-in.

## Step 3: undo of BROKER-284
`sudo bash /tmp/dev-sign-in-install-BROKER-284.sh undo` printed "Removed. The sign-in rules are gone and nginx was reloaded."

| Check (2 s after) | Expected | Result |
|---|---|---|
| `/_allauth/browser/v1/config` via 10.0.0.1 | `404` | `404` |
| `/accounts/google/login/callback/?error=access_denied` via 10.0.0.1 | `404` | `404` |
| the same two via 127.0.0.1 | `404` | `404`, `404` (so the website's gate answered `404` there, as you expected) |
| site file vs `...before-284` (`cmp`) | identical | `identical` |
| `/etc/nginx/snippets/ddp-broker-sign-in.conf`, `/etc/nginx/conf.d/ddp-broker-sign-in-zone.conf` | gone | both gone |
| `api.../docs`, `dev /` | `200`, `200` | `200`, `200` |

All matched, so I went on to step 4.

## Step 4: close for BROKER-289
`sudo bash /tmp/close-public-admin-BROKER-289.sh close` printed `Backup: /etc/nginx/sites-available/dev.digitaldemocracyproject.org.before-289` and "Closed and nginx reloaded: /admin and /static on the public dev address now answer 404."

| Check (2 s after) | Expected | Result |
|---|---|---|
| `/admin`, `/admin/`, `/admin/login/`, `/static/admin/css/base.css` via 10.0.0.1 | `404` | `404`, `404`, `404`, `404` |
| the same four via 127.0.0.1 | `404` | `404`, `404`, `404`, `404` |
| `dev /` | `200` | `200` |
| `api.../docs` | `200` | `200` |
| `grep -c 'BROKER-289'` in the dev site file | `3` | `3` |
| `nginx -t` | ok | syntax ok, test successful |

(Before this step, `/admin/login/` and `/static/admin/css/base.css` were `200` over the tunnel address, as reported in the pre-flight note.)

## Did anything else change?
No. `diff` of the site file against the new backup `...before-289` shows exactly three added lines and nothing removed:
```
15a16  >     return 404; # BROKER-289: closed, staff use admin-dev
27a29  >     return 404; # BROKER-289: closed, staff use admin-dev
39a42  >     return 404; # BROKER-289: closed, staff use admin-dev
```
The `/` block, the edge secret, the certificates, `api.*`, `votebot`, ddp-api, ddp-sync and the broker host were not touched. Two reloads only, no restart.

## nginx error log
The last lines are only the two `signal process started` notices from my two reloads (00:46:06 and 00:46:23). Nothing else new, no errors, no `access forbidden by rule` lines.

## State now and rollback (not needed)
- The site file is the original plus the three `return 404;` lines. Backups `...before-284` and `...before-289` are in place.
- Close: `sudo bash /tmp/close-public-admin-BROKER-289.sh reopen`.
- BROKER-284 rules back: `sudo bash /tmp/dev-sign-in-install-BROKER-284.sh install`.
- I will not run either unless Ramon asks.

## For Ramon
Please check from your side that `https://admin-dev.digitaldemocracyproject.org/admin/login/` still works (nothing here touches it). `https://dev.digitaldemocracyproject.org/admin/...` now answers 404 from every address, which is the intended result; the website's "Staff tools" links will show that until NEXT-66.
