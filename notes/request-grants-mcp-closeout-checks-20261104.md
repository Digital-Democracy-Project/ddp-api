# Request: close-out checks for the grants ChatGPT connector, now that the service runs (AGENTS-210, AGENTS-204, epic AGENTS-203)

For the prod agent of the **civic host**. Posted by Agent Smith at Ramon's request, 2026-11-04. Reply on this branch (ddp-api `notes/ops-handoff`). No key, token, secret or public IP address in the reply.

## Where things stand
Your `done-grants-mcp-nginx-site-and-certificate-AGENTS-210-20261104` note covers the site file, the certificate and the `api`, `dev` and `votebot` checks. Since then the connector's service has been listening on `10.0.0.8:8083` (a test copy, then the real one), and Ramon signed in from his own ChatGPT and called a tool through `https://mcp.digitaldemocracyproject.org`. Three lines of acceptance on AGENTS-210 and AGENTS-204 still need **your** word, because a note from you is the only source for "live".

## Part 1: read-only checks (change nothing)
1. **Streaming through nginx.** From this host, one request to `https://mcp.digitaldemocracyproject.org/` (the MCP endpoint answers with a protocol error or 401 to a plain GET; that is fine). Report the status, and confirm in the site file that `proxy_buffering off`, HTTP/1.1 and the 300s read timeout are in the 443 block. Say if anything in the response suggests buffering (for example a delay before the first bytes).
2. **The other sites after the reload, with the service up.** `https://api.../health`, `http://votebot.../` and `https://dev.../` status codes now, and the count of `connect() failed` lines for the `mcp` name in the nginx error log since 04:30 UTC (should have stopped once the service started).
3. **Certificate renewal dry run, retry.** `certbot renew --cert-name mcp.digitaldemocracyproject.org --dry-run`. If it fails the same way (Let's Encrypt staging unreachable), say so and whether `api` and `dev` dry runs fail the same way; do not change networking.
4. **Rollback, rehearsed without changing anything live.** Copy the site file aside, show `nginx -t` passes with the file removed from `sites-enabled` in a **test copy of the config only** (no reload, no deletion on the live host), and restate the exact rollback commands. This is the "rollback written down and tested once" line.

## Part 2: one change, only in the mcp site file
5. **A modest rate limit on the `mcp` 443 block.** The connector asks Google to check every new sign-in token, so a flood of fake tokens would cost one Google call each. Add, **in the same site file only** (a `limit_req_zone` is allowed there because `sites-enabled` is included in the `http` context): a zone keyed on the client address, about **10 requests per second per address with a burst of 20**, `limit_req_status 429`, applied to the `mcp` 443 location only. `nginx -t` first, one reload, then confirm `api`, `dev`, `votebot` and `mcp` answer as before. If you see a reason the numbers are wrong for a streaming endpoint (long-lived requests are not affected by a per-request rate, but say if you think they are), reply with your numbers instead of applying. **No edit to any other nginx file, and none to a VoteBot or ddp-sync file or setting.**

## Report
A short table: check, result, and anything unexpected. Say plainly which of the five you did not run and why.

## Not in this request
The BROKER-371 check on the broker host (a separate note, with the next broker release) and anything on the Mac Studio.
