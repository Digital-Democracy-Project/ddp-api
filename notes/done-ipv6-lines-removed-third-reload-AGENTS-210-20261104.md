> **Follow-up to** `correction-done-note-missed-addendum-ipv6-lines-AGENTS-210-20261104.md` (AGENTS-210, epic AGENTS-203). Posted on **this** branch (ddp-api `notes/ops-handoff`). **The IPv6 `listen` lines are removed from the mcp file and nginx was reloaded a third time.** No key, secret or public IP address is in this note.

# Done (2026-11-04): IPv6 lines removed, third reload, `api` and `votebot` unchanged

Run on the civic host, on the in-session yes for the third reload (the correction note had said it was beyond Ramon's two).

## What was changed
- In `/etc/nginx/sites-available/mcp.digitaldemocracyproject.org` only: the three lines `listen [::]:80;` (port-80 block), `listen [::]:443 ssl;` (443 block) and nothing else were removed. Diff against a copy taken just before showed exactly those two deleted lines (the earlier note said "three"; the correct count is **two**: one in each block). The file now has `listen 80;` and `listen 443 ssl;`.
- `nginx -t` ok, then reload 3. No other file touched.

## Before and after (the addendum's point 2, this time with a before-state)
| Check | Before reload 3 | After reload 3 |
|---|---|---|
| Certificate for an unknown name over https | `CN = api.digitaldemocracyproject.org`, expires Dec 5 2026 | identical |
| `https://api.../health` | `200` | `200` |
| `http://votebot.../` | `200` | `200` |
| `https://dev.../` | `200` | `200` |
| `http://mcp.../health` | `200` (DDP-API) | `200` |
| `https://mcp.../` | `502`, certificate verifies | `502`, certificate verifies |
| Listening sockets on 80/443 | `0.0.0.0:80`, `0.0.0.0:443`, `[::]:80`, `[::]:443` | `0.0.0.0:80`, `0.0.0.0:443`, `[::]:80` |

The `[::]:443` socket is gone, so no IPv6 https request can land on the mcp server. `[::]:80` is still open because the default site listens on it, as before this work.

## Totals
Three reloads for the whole job (journal count for the hour: 3): the port-80 block, the 443 block, the IPv6 removal. Certbot did not reload nginx itself.

## Still open
- The renewal dry run did not run (Let's Encrypt staging unreachable from this host); see the done-note.
- `10.0.0.8:8083` is not running yet, so `https://mcp...` answers 502 as expected.
