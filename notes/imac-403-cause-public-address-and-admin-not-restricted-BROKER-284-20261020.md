> **Reply to** `request-read-only-why-imac-gets-403-on-sign-in-BROKER-284-20261020.md` (BROKER-284). Replying on **this** branch (ddp-api `notes/ops-handoff`). **No changes were made, nothing was restarted or reloaded.** No key, secret or public IP address is in this note (the `X-DDP-Edge` value is redacted).

# Answer (2026-10-20, about 21:05 UTC): the iMac reaches this host from a public address, not through the tunnel. Separately, `/admin/` is not restricted on this host.

Everything was run read-only on the host (`ip-172-31-81-51`).

## Short answer
- The 403s are the new rule working as designed. The client address nginx sees for the iMac is **public (not shown)**, so `allow 10.0.0.0/24; deny all;` refuses it.
- So the iMac's traffic to this host is **not going through the tunnel**. The allow range is not wrong; nothing needs to change on this host for this. The fix is on the iMac's VPN settings (or a hosts entry there that points the dev name at `10.0.0.1`).
- **Discrepancy to tell Ramon about:** the real dev site file has **no `allow`/`deny` lines at all**, so `/admin/` is reachable from any address on this host. That is why `/admin/login/` loads for the iMac while `/_allauth/` is refused. This is an existing exposure, not something the install created (see 3).

## 1. Error log (`access forbidden by rule`, dev site, last 2 hours)
5 lines, **all with a public client address (not shown)**; none from a `10.0.0.x` address:

| Count | Client | Method and path |
|---|---|---|
| 3 | public (not shown) | `POST /_allauth/browser/v1/auth/provider/redirect` |
| 1 | public (not shown) | `GET /_allauth/browser/v1/config` |
| 1 | public (not shown) | `GET /accounts/google/login/callback/` |

The three `POST`s match the iMac attempts in the access log (2). The two `GET`s are most likely the dev agent's own checks from the Mac Studio over the public internet, which the request says to expect; I did not verify that, and the address is public either way.

## 2. Access log (`/var/log/nginx/access.log`, shared by all sites; no per-site log for dev)
The iMac's attempts today, all from **one and the same public client address** (called "public #1" here), `GET /admin/login/` then `POST .../redirect`:

| Time (UTC) | `GET /admin/login/?next=/admin/` | `POST /_allauth/browser/v1/auth/provider/redirect` |
|---|---|---|
| 20:50:33 / 20:50:34 | 200 | **403** |
| 20:52:15 (GET), 20:52:09 and 20:52:18 (POST) | 200 | **403**, **403** |

- Same client address for the page load and the sign-in click, in every pair: **yes**, and it is public, not `10.0.0.x`.
- Earlier the same address got `404` on the same `POST` (03:58 to 04:30 UTC). That was **before** the install (the 18:47 site file change), when nothing forwarded the path. It shows the same address was already coming in over the public internet then.
- The only `10.0.0.x` client in the dev-site lines for these two paths is `10.0.0.8` (the Mac Studio), one `GET /admin/login/` at 04:01 UTC, 200.

## 3. The real location/allow/deny lines (`grep -n -E '^\s*(location|allow|deny)'` on the dev site file)
```
16:  location = /admin {
28:  location ^~ /admin/ {
40:  location ^~ /static/ {
52:  location / {
```
**No `allow` and no `deny` line anywhere in the file.** The new rules are not in this file; they come from the included snippet (`include /etc/nginx/snippets/ddp-broker-sign-in.conf;`, line 13). I also read the four blocks in full (secret redacted): `= /admin` and `^~ /admin/` are plain `proxy_pass http://10.0.0.8:3000` with the `X-DDP-Edge` header, with no address restriction. So on this host `/admin/` is open to any address, **wider than the saved copy in ddp-next**, which the request says restricts it to `10.0.0.0/24`. The earlier install note's "same rule as `/admin`" assumption therefore does not hold on the real host. I did not change it; whether to restrict it is Ramon's call.

## 4. IPv6
- `nginx -T | grep 'listen .*443'`: the dev site has one listener, `listen 443 ssl;` (IPv4 only). The other lines are the `api.*` site (`listen 443 ssl; # managed by Certbot`) and a commented-out default-server block. **No IPv6 listener** for the dev site.
- `dig +short AAAA dev.digitaldemocracyproject.org`: **no record**.
- The host has no global IPv6 address either.
So IPv6 is not the cause.

## What I did not do
No change of any kind, no reload, no sign-in attempt. I did not touch the `/admin` blocks or run the `undo`.

## Suggested next steps (for Ramon to decide)
1. **iMac:** make the WireGuard peer route this host's tunnel address, or put `10.0.0.1 dev.digitaldemocracyproject.org` in the iMac's hosts file (same trick the dev agent used with `--resolve`). Then retry; the source should be a `10.0.0.x`.
2. **`/admin/`:** if it is meant to be VPN-only, an `allow 10.0.0.0/24; deny all;` pair in the two `/admin` blocks would do it. Ask ops for that as a separate, explicit request. Note that doing it before step 1 would also lock the iMac out of `/admin/login/`.
