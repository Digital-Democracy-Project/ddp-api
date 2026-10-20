> **Reply to** `request-install-dev-sign-in-rules-for-staff-google-login-BROKER-284-20261020.md` (BROKER-284, ddp-broker-py PR #491). Replying on **this** branch (ddp-api `notes/ops-handoff`). No key, secret or credential is in this note.

# Done (2026-10-20): the sign-in rules are installed on the ddp-api host, nginx reloaded, all checks as expected

Everything was run on the host (`ip-172-31-81-51`). The script was byte-identical to the one on this branch (checked with `diff` before running). I did **not** try a Google sign-in.

## Step 1: read-only pre-flight (nothing changed)
| Check | Expected | Result |
|---|---|---|
| `dev.digitaldemocracyproject.org` in `sites-enabled` | symlink to `sites-available` | yes |
| `listen 443 ssl` lines | exactly one | one (line 12) |
| `location` blocks | `= /admin`, `^~ /admin/`, `^~ /static/`, `/` | exactly those four, nothing else |
| `nginx -t` | ok | ok |
| `include /etc/nginx/conf.d/*.conf;` | present | present (line 60 of `nginx -T`) |
| `broker_sign_in` / `ddp-broker-sign-in` | none | none |
| `api.../docs`, `dev /` | 200, 200 | 200, 200 |
| `/_allauth/browser/v1/config` via 10.0.0.1 (before) | 404 | 404 |

The site file as it was (secret line left out; the grep does not match it):
```
6:  listen 80;
7:  server_name dev.digitaldemocracyproject.org;
8:  return 301 https://$server_name$request_uri;
12:  listen 443 ssl;
13:  server_name dev.digitaldemocracyproject.org;
15:  location = /admin {
27:  location ^~ /admin/ {
39:  location ^~ /static/ {
51:  location / {
69:  ssl_certificate /etc/letsencrypt/live/dev.digitaldemocracyproject.org/fullchain.pem; # managed by Certbot
70:  ssl_certificate_key /etc/letsencrypt/live/dev.digitaldemocracyproject.org/privkey.pem; # managed by Certbot
```

## Step 3: install
`sudo bash /tmp/dev-sign-in-install-BROKER-284.sh install` printed `Backup: /etc/nginx/sites-available/dev.digitaldemocracyproject.org.before-284` and then `Installed and nginx reloaded.` The include line is now line 13 of the site file, right after `listen 443 ssl;`.

## Step 4: checks (2 s after the reload)
| Check | Expected | Result |
|---|---|---|
| `/_allauth/browser/v1/config` via 10.0.0.1 | JSON containing `"google"` | JSON, `google` in `socialaccount.providers` |
| `/accounts/google/login/callback/?error=access_denied` via 10.0.0.1 | 302 | 302 |
| `/_allauth/browser/v1/config` via 127.0.0.1 | 403 | 403 |
| `/accounts/google/login/callback/` via 127.0.0.1 | 403 | 403 |
| `api.../docs` | 200 | 200 |
| `dev /` | 200 | 200 |

## nginx error log
The only new lines after the reload are two `access forbidden by rule` entries from my own 127.0.0.1 checks (the intended 403s). Older `SSL_do_handshake() failed (bad key share)` entries from outside addresses started before the install (scanner noise) and are unrelated.

## For Ramon
The click-through from the iMac on the VPN is yours. If it shows 403, the likely cause is the iMac's WireGuard not routing this host through the tunnel (as the request notes), not the rules.

## Rollback (not needed)
`sudo bash /tmp/dev-sign-in-install-BROKER-284.sh undo`. The backup `...dev.digitaldemocracyproject.org.before-284` is in place.

## Not covered here
The API-12 request (deploy broker `28fdb2f5`, 2026-10-09) is a separate note. I did not act on it in this session.
