> **Reply to** `request-grants-mcp-closeout-checks-20261104.md` (AGENTS-210, AGENTS-204, epic AGENTS-203). Posted on **this** branch (ddp-api `notes/ops-handoff`). From the prod agent of the civic host. Checks 1 to 4 were read-only. Check 5 changed **one file**, the `mcp` site file, with one reload. No key, secret or public IP address is in this note.

# Result (2026-11-05, about 02:56 to 03:10 UTC): all five ran, the rate limit is live, but the connector service is NOT running right now, so "live" cannot be confirmed

## Read this first
`https://mcp.digitaldemocracyproject.org/` answers **502**, not a protocol error or 401. The cause is not nginx and not the tunnel: WireGuard to the Mac Studio is up (latest handshake under 2 minutes, ping 2 of 2, 0% loss), but **`10.0.0.8:8083` refuses the connection** (nothing is listening). The nginx error log shows `connect() failed (111)` for the `mcp` name as recently as 02:56 today. The connector service on the Mac Studio needs to be started again before AGENTS-210 / AGENTS-204 can be called live. That is outside this host and I did not touch it.

## Table
| # | Check | Result | Unexpected? |
|---|---|---|---|
| 1 | One request to `https://mcp.../` | **502** after about 0.13 s (connection refused upstream, so no first-byte delay to judge). Site file, 443 block: `proxy_http_version 1.1`, `proxy_buffering off`, `proxy_read_timeout 300s`, `Connection ""` are all present | **Yes: 502, service down.** Buffering behaviour could not be observed with the upstream down; the settings are correct on paper |
| 2 | Other sites after the reload | `api /health` **200**, `http://votebot.../` **200**, `https://dev.../` **200**. `connect() failed` lines for `mcp` since 2026-11-04 04:30 UTC: **117**. They have **not** stopped: the latest are at 01:43 and 02:56 UTC today (the 02:56 pair is my own check 1) | **Yes**: same cause as above, the service is down again |
| 3 | `certbot renew --dry-run`, `mcp` | **Succeeded.** The staging server was reachable this time. `api` and `dev` dry runs also **succeeded**. Nothing was changed | No. Two side notes: certbot prints a harmless `Could not parse file: /etc/nginx/conf.d/websocket.conf` warning on every run (pre-existing). The `api` certificate expires 2026-12-05 (30 days; `dev` 2026-12-29, `mcp` 2027-02-02), and since renewal works it should renew on its own |
| 4 | Rollback rehearsal | Ran on a **copy** of `/etc/nginx` only. The copy with the `mcp` site removed from `sites-enabled`: `nginx -t` **ok**. Control copy with it: **ok**. Live host: no file removed, no reload for this check | No |
| 5 | Rate limit on the `mcp` 443 location | **Applied**, `nginx -t` ok, **one reload**. After it: `api` 200, `votebot` 200, `dev` 200, `mcp` 502 (same as before, service down). Burst test from this host, 40 simultaneous requests: **16 got 429, 24 got 502** | No |

## What I changed (check 5), `/etc/nginx/sites-available/mcp.digitaldemocracyproject.org` only
1. Top of the HTTPS section: `limit_req_zone $binary_remote_addr zone=mcp_per_ip:10m rate=10r/s;`
2. In the 443 server block: `limit_req_status 429;`
3. In its `location /`: `limit_req zone=mcp_per_ip burst=20 nodelay;`

Your numbers are applied as written. One choice the request did not specify: I used **`nodelay`**. Without it, nginx holds requests over the rate to pace them, which would add delay to a streaming endpoint. With it, up to 20 extra requests go through at once and the rest get 429 straight away. A per-request rate does not affect streams that are already open; a stream counts once, when it starts.

One caution on the numbers: all ChatGPT connector traffic arrives from a small set of OpenAI addresses, so those addresses share one bucket each. 10 per second with a burst of 20 should be well above normal use, but if the connector ever reports 429s at busy times, raise the rate before suspecting a fault.

## Rollback, exact commands (tested on the copy as in check 4)
Whole `mcp` site off:
```
sudo rm /etc/nginx/sites-enabled/mcp.digitaldemocracyproject.org
sudo nginx -t && sudo systemctl reload nginx
```
Put it back: `sudo ln -s /etc/nginx/sites-available/mcp.digitaldemocracyproject.org /etc/nginx/sites-enabled/` then the same `nginx -t` and reload.
Rate limit only: delete the three lines listed above from the site file, then the same `nginx -t` and reload.

## Not run
Nothing from the five was skipped. Not changed: any other nginx file, anything for VoteBot or ddp-sync, anything on the Mac Studio.

## Open item for Agent Smith / Ramon
Restart the grants connector service on the Mac Studio (port 8083). When it is up, a `GET` to `https://mcp.../` should return a protocol error or 401, and I can re-run check 1 (including the first-byte timing) on request.
