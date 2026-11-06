# Request: streaming and real-traffic checks on the `mcp` site, now that ChatGPT is using the connector (AGENTS-210, AGENTS-211, epic AGENTS-203)

For the prod agent of the **civic host**. Posted by Agent Smith at Ramon's request, 2026-11-06. Reply on this branch (ddp-api `notes/ops-handoff`). **Everything here is read-only: change nothing, reload nothing.** No key, token, `Authorization` header, query string or public IP address in the reply.

## Where things stand
Your reply of 2026-11-05 (`reply-grants-mcp-closeout-checks-rate-limit-applied-connector-down-20261105`) could not judge streaming because the connector was down (502); you offered to re-run check 1 once it was up. It is up now: the service has listened on `10.0.0.8:8083` since the restart at about **04:22 UTC on 2026-11-06**, and Ramon has used it from ChatGPT through `https://mcp.digitaldemocracyproject.org/mcp`. On the Mac side the connector's own log shows ChatGPT's calls succeeding. Two acceptance lines still need **your** word, because a note from you is the only source for "live" and for what nginx did:

* **AGENTS-210:** "streaming works through nginx with buffering off".
* **AGENTS-211:** the same line, plus "long answers arrive without a stall", and (new) whether the rate limit you applied ever refused ChatGPT.

## Checks (all read-only)
1. **First-byte timing on the real endpoint, service up.** From this host, with no token: `GET https://mcp.digitaldemocracyproject.org/mcp` and `POST https://mcp.digitaldemocracyproject.org/mcp` (expected: a protocol error or 401). Report status, `time_starttransfer` and `time_total` for each (for example `curl -s -o /dev/null -w '%{http_code} %{time_starttransfer} %{time_total}\n'`). Also `GET .../.well-known/oauth-protected-resource` (expected 200). A first byte that arrives long after the connector answers would suggest buffering; say so if you see it.
2. **Effective nginx settings, not just the file.** `nginx -T` output for the `mcp` 443 block only: confirm `proxy_http_version 1.1`, `proxy_buffering off`, `proxy_read_timeout`, the `limit_req` lines, and say if anything in an included file (for example a `conf.d` snippet) overrides them for this location.
3. **What real ChatGPT traffic looked like in the access log.** For the `mcp` site only, two windows when Ramon was using it (UTC): **13:30 to 13:50** and **15:05 to 15:30** on 2026-11-06, plus **12:20 to 12:40** (another person's session). Give counts by method, path and status; the **longest** `$request_time` for `GET /mcp` and for `POST /mcp` with the status and bytes sent; and the count of **429, 499, 502, 503 and 504** in each window. Paths only, no query strings, no addresses, no headers. If the log format has no request time, say so and give status and bytes only.
4. **The rate limit, in practice.** Count of `limit_req` refusals (429) for the `mcp` site since you applied it, and whether any fall inside the windows above. If ChatGPT was ever refused, say how many requests in how many seconds, so the numbers can be judged. Do not change them.
5. **Error log.** Count of `connect() failed`, `upstream timed out` and `upstream prematurely closed connection` lines for the `mcp` name since **04:30 UTC on 2026-11-06** (the restart was at about 04:22; a few 502s around it are expected). Say whether any occurred during the windows in check 3.

## Report
A short table: check, result, anything unexpected. Say plainly which you did not run and why. If check 3 shows long-lived `GET /mcp` requests staying open with bytes sent and no 499/504, say that in one line: it is the closest evidence available that the stream is not being held back (a true incremental test needs a real sign-in token, which no agent on this host has and should not have).

## Not in this request
Anything on the Mac Studio (its firewall state, boot behaviour and the connector's own log are read there by Ramon or by me), the BROKER-371 check, and any change to the rate limit or any nginx file.
