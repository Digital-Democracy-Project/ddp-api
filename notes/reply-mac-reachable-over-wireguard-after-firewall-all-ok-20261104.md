> **Reply to** `request-mac-reachable-over-wireguard-after-firewall-20261104.md` (AGENTS-210, epic AGENTS-203). Posted on **this** branch (ddp-api `notes/ops-handoff`). **Read-only: ping, connect-only TCP tests, web requests and log counts. Nothing was changed on this host.** No key, secret or public IP address is in this note.

# Result (2026-11-04, run at about 04:29 UTC, about 4 minutes after the rule): everything as expected, nothing looks wrong

## Table
| Check | Expected | Result |
|---|---|---|
| WireGuard, Mac peer `10.0.0.8` latest handshake | under 2 minutes | **5 seconds ago** |
| `ping -c 4 10.0.0.8` | 0% loss, about 20 ms | **4 of 4, 0% loss, 11.3 / 14.4 / 18.4 ms (min/avg/max)** |
| `10.0.0.8:3000` (what `dev` proxies to) | open | **open** |
| `10.0.0.8:8000` | open | **open** |
| `10.0.0.8:8002` | open | **open** |
| `10.0.0.8:8080` | open | **open** |
| `10.0.0.8:8081` | open | **open** |
| `10.0.0.8:8083` (connector, not running) | **refused** (good) | **refused**: this host gets through the firewall to a port with nothing listening; not a timeout |
| `https://dev.../` | 200 | **200** |
| `https://api.../health` | 200 | **200** |
| `http://votebot.../` | 200 | **200** |
| `https://mcp.../` | 502, certificate verifies | **502**, certificate verifies |

Connect tests used a 5-second timeout and sent nothing. No port timed out.

## What is different from Step 0
- Ping latency is a little lower (about 14 ms average against about 20 ms), and the handshake is fresher. Nothing worse.
- **Limit of the comparison:** Step 0 only tested `10.0.0.8:8083` (refused then, refused now) and ping. I had **no earlier reading** for ports 3000, 8000, 8002, 8080 and 8081, so "open" now cannot be compared with "open before". What supports them being unaffected: all five connect, and `dev` (which proxies to 3000) returns 200.

## Logs (counts only)
Since 04:25 UTC the nginx error log has **3** `connect() failed` lines mentioning `10.0.0.8`, all for `server: mcp.digitaldemocracyproject.org`: the 502s from requests to the not-yet-running connector (several of them were my own checks). None for `dev` or any other server. I did not look at other services' logs on this host.

## Caveat on timing
The check ran about 4 minutes after the rule, so it shows the state right now. A later timeout (for example if pf state is reloaded) would not appear in it. If the rule changes or pf restarts, the same checks are quick to rerun.

## Anything wrong?
No. Nothing for Ramon to undo.
