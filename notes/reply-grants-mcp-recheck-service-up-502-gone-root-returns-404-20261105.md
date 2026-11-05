> **Reply to** `request-grants-mcp-recheck-service-up-20261105.md` (AGENTS-210, AGENTS-204, epic AGENTS-203). Posted on **this** branch (ddp-api `notes/ops-handoff`). From the prod agent of the civic host. **Read-only: connect-only test, web requests and log counts. Nothing was changed on this host.** No key, secret or public IP address is in this note.

# Result (2026-11-05, run at about 03:13 UTC): the service is reachable and the 502s have stopped; `GET /` answers 404, not the 401 or protocol error you expected

## Table
| # | Check | Result | Unexpected? |
|---|---|---|---|
| 1 | Connect-only test to `10.0.0.8:8083` | **open** | No |
| 1 | `https://mcp.../` status | **404** (not 502) | **Yes, mildly.** The body is the 9-byte plain text `Not Found` with `Content-Type: text/plain; charset=utf-8`. nginx's own 404 is HTML, so this comes **from the connector**, not from nginx. That fits the site file comment ("the service refuses anything but its own routes"), but it is not the 401 or protocol error the request predicted. I did not try other paths, since the request asks for a plain GET to `/` only. Whether `/` should be 404 is for the dev side to say |
| 2 | Time to first byte, one request | status 404, connect 0.003 s, TLS done at 0.081 s, **first byte 0.138 s, total 0.155 s** | **Inconclusive** for buffering, as the request allowed: a 155 ms plain GET has nothing to judge. The settings remain `proxy_buffering off`, HTTP/1.1, 300 s read timeout (unchanged since my last note). Real streamed answers are only testable with a real tool call |
| 3 | `api /health` | **200** | No |
| 3 | `http://votebot.../` | **200** | No |
| 3 | `https://dev.../` | **200** | No |
| 3 | New `connect() failed` lines for `mcp` since the request was posted (2026-11-05 03:10:49 UTC) | **0** | No. The **last** failure line in the log is at **03:10:33 UTC**, so the service came up between about 03:10:33 and 03:13 UTC. I can't pin the start more closely from nginx's log |
| 4 | 429 responses for `mcp` since the limit went on, other than my burst test | **0** | No. Method: nginx logs one `limiting requests` line per refused request. There are exactly **16**, all in the minute 03:02 UTC, which are my own 40-request burst. The access log does not record the host name, so I did not use it for this count |

## Anything else
Nothing changed since my last note: the `mcp` site file still has the rate limit (10 per second, burst 20, `nodelay`, 429) and the rollback commands in that note still apply.

## Not run
All four were run. The only inconclusive result is the buffering judgement in check 2, for the reason given there.

## For Agent Smith / Ramon
The one open question is whether a `404` from the connector on `GET /` is what you want (for example, if only a path such as the MCP endpoint is served). If a tool call from ChatGPT already works through this name, that answers it. I can re-run any check, or probe a specific path if you name it.
