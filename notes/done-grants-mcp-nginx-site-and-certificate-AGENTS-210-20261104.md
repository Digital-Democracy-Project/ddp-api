> **Reply to** `reply-grants-mcp-nginx-certificate-decision-20261104.md` (AGENTS-210, epic AGENTS-203). Replying on **this** branch (ddp-api `notes/ops-handoff`). **Done: one new site file, one certificate, two reloads. One check did not run: the renewal dry run (see below).** No key, secret or public IP address is in this note.

# Done (2026-11-04): `mcp.digitaldemocracyproject.org` site and certificate in place; answers 502 until the Mac Studio service runs

Run on the civic host (`ip-172-31-81-51`), after Ramon's decisions (certificate by web proof, port 80 left as is) and the go-ahead given in session.

## What was changed
- **One new file:** `/etc/nginx/sites-available/mcp.digitaldemocracyproject.org`, enabled with the usual symlink in `sites-enabled` (same pattern as `api` and `dev`). No other nginx file was edited (modified-file check over `/etc/nginx` showed only this file and its symlink). ddp-sync and votebot untouched.
- **One certificate:** `certbot certonly --nginx -d mcp.digitaldemocracyproject.org` (existing certbot account, the nginx plugin, as for `api` and `dev`). Expires 2027-02-02. Nothing was installed. Certbot's own scheduled renewal covers it.
- **Reload 1:** the file with only the port-80 block (`nginx -t` ok, then reload).
- **Reload 2:** the 443 block from the request appended to the same file, with the two certificate lines for the new name (`nginx -t` ok, then reload). The journal shows exactly 2 reloads for the whole sequence: certbot did not reload nginx itself.

## Port 80 (decision 2: leave it)
The port-80 block has `listen 80` and `listen [::]:80`, and keeps non-challenge paths behaving as before: `location /` and `location /votebot/ws` proxy to `127.0.0.1:5000` with the same headers as the default site. `http://mcp.../health` returned `200` before and after (DDP-API). No redirect to https was added.

## Results
| Check | Result |
|---|---|
| `nginx -t` before reload 1 / before reload 2 | syntax ok, test successful (both) |
| `https://api.../health` after each reload | `200` |
| `http://votebot.../` after each reload | `200` |
| `https://dev.../` after each reload | `200` |
| `http://mcp.../health` after each reload | `200` |
| `https://mcp.../` with certificate verification | `502`, `ssl_verify_result=0` (certificate verifies; upstream refuses, as expected) |
| Certificate served for the name | `CN = mcp.digitaldemocracyproject.org`, issuer Let's Encrypt, expires 2027-02-02 |
| Renewal config | `authenticator = nginx`, `installer = nginx`, production server: same as `api` and `dev` |
| nginx error log | upstream `connect() failed (111)` for the new name (the service is not running yet); one unrelated TLS scanner line |

## Not completed: renewal dry run
`certbot renew --cert-name mcp.digitaldemocracyproject.org --dry-run` **failed**: connection reset by peer on its first request, to Let's Encrypt's **staging** directory. From this host the staging endpoint times out (three tries), while the production endpoint answers `200`. So this is staging reachability from the host, not the site or the certificate (no challenge was attempted, and the real issuance worked). The renewal config matches the other two certificates, so renewal should behave the same, but it is **not proven by a dry run**. Suggest a retry later, or check whether this host's network filters the staging name.

## Other things noticed
- Certbot prints `Could not parse file: /etc/nginx/conf.d/websocket.conf` on every run (a `map` file its parser does not read). It is harmless, and the same message would appear for the `api` and `dev` renewals. Not changed.
- The 443 block uses only the two certificate lines, as requested. `api` also includes `options-ssl-nginx.conf`; `dev` does not. Not added.

## Left for others, as in the request
The Mac Studio firewall rule, the connector's background service, the read-only database login, the Google sign-in client and the ChatGPT setting. After the service listens on `10.0.0.8:8083`, the 502 should turn into real answers. The streaming check comes with AGENTS-204.

## Rollback (not needed)
Delete the symlink and the file, `nginx -t`, reload, confirm `api`, `dev` and `votebot`; then `certbot delete --cert-name mcp.digitaldemocracyproject.org`; Ramon removes the Cloudflare record.
