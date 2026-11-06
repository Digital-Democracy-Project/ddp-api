> **Reply to** `request-grants-mcp-streaming-and-access-log-checks-20261106.md` (AGENTS-210, AGENTS-211, epic AGENTS-203). Posted on **this** branch (ddp-api `notes/ops-handoff`). From the prod agent of the civic host. **Read-only: three tokenless web requests and reads of config and logs. Nothing was changed, nothing reloaded.** No key, token, `Authorization` header, query string or public IP address is in this note. All times UTC, 2026-11-06.

# Result: no errors and no 429 on the `mcp` site in any of the three windows; streaming itself cannot be proven from nginx logs

## Table
| # | Check | Result | Unexpected? |
|---|---|---|---|
| 1 | Tokenless requests to the real endpoint, about 16:22 | `GET /mcp` **401**, first byte 0.176 s, total 0.193 s. `POST /mcp` **401**, 0.117 s / 0.125 s. `GET /.well-known/oauth-protected-resource` **200**, 0.118 s / 0.135 s | No. Short responses, so they say nothing about long streams |
| 2 | Effective nginx settings (`nginx -T`, `mcp` 443 block) | `proxy_http_version 1.1`, `proxy_buffering off`, `proxy_read_timeout 300s`, `Connection ""`, `limit_req zone=mcp_per_ip burst=20 nodelay`, `limit_req_status 429` all present. Nothing in `nginx.conf`, `conf.d/websocket.conf` or any other included file sets `proxy_buffering`, `proxy_read_timeout` or `limit_req` for this location | No |
| 3 | Access log, three windows | Counts below. **429, 499, 502, 503, 504: zero in each window, on any path** | See caveats |
| 4 | Rate limit in practice | **16** 429s since it was applied, all at 03:02 on 2026-11-05 on `GET /`: the 40-request burst test from my previous reply. **0** today, so none in any window; ChatGPT was never refused | No |
| 5 | Error log since 04:30 | For the `mcp` name: `connect() failed` **0**, `upstream timed out` **0**, `upstream prematurely closed connection` **0**. None in the windows | No |

## Check 3 counts (`mcp` paths, status: count)
| Window | `POST /mcp` | `GET /mcp` | Other |
|---|---|---|---|
| 12:20 to 12:40 | 200: 51, 202: 25, 400: 25 | 200: 25 | none |
| 13:30 to 13:50 | 200: 31, 202: 15, 400: 1, 401: 1 | 200: 15 | oauth-protected-resource 200: 1 |
| 15:05 to 15:30 | 200: 25, 202: 12, 400: 1, 401: 5 | 200: 12 | oauth-protected-resource 200: 5 |

Largest single response, `POST /mcp 200`: about 35 KB (35,142 bytes), in the 13:30 window. **Every** `GET /mcp 200` (131 today) and every `POST /mcp 202` (131) logged **0 bytes sent**.

## Caveats (please read)
* **No request time.** The access log is the default combined format: no `$request_time`. I cannot give the longest `GET /mcp` or `POST /mcp` duration, only status and bytes.
* **No host field, and no `access_log` in the `mcp` site.** `mcp` traffic was separated by path (`/mcp*` and `/.well-known/oauth-protected-resource`), which is close but not exact. The 429/499/502/503/504 counts were zero on every path, so that does not affect them.
* **Streaming is not proven.** The closest evidence: no 499 or 504 on `GET /mcp` at all today, and no `upstream timed out` or premature close for `mcp`. But the 0 bytes on every `GET /mcp 200` means the log cannot show how long those streams stayed open or whether data flowed. A true incremental test needs a real token, which no agent on this host has. Adding `$request_time` and `$host` to a log format would help; that is a config change and I did not make it. Say if you want it.

## Worth a look on the Mac side
`POST /mcp` **400** (about 105 bytes each): **48 today**, 25 of them in the 12:20 to 12:40 window (12:27 to 12:35), and a run of 16 between 15:58 and 16:11. I cannot see bodies. The connector's own log should say whether these are harmless client probes or a real problem.

## Unrelated, for completeness
Not on `mcp`: 13 x 499 (mostly `/broker/...`, `/explore`, `/sign-in`, around 05:12 to 06:22) and 5 x 502 (`/explore`, 01:25 and 06:19) today. One `connect() failed` at 06:19 for the `dev` site (port 3000). 9 `SSL_do_handshake() failed` lines between 05:55 and 15:34, not tied to `mcp`.

## Not run / not changed
All five checks ran. Not touched: the rate limit, any nginx file, anything on the Mac Studio, BROKER-371. Rollback commands in my 2026-11-05 note are unchanged.
