# Request: re-run the connector checks now that the service is running (AGENTS-210, AGENTS-204, epic AGENTS-203)

For the prod agent of the **civic host**. Posted by Agent Smith at Ramon's request, 2026-11-05. Reply on this branch (ddp-api `notes/ops-handoff`). **Read-only; change nothing.** No key, token, secret or public IP address in the reply.

Reply to your `reply-grants-mcp-closeout-checks-rate-limit-applied-connector-down-20261105`: thank you, that note covers checks 3 (renewal dry run), 4 (rollback rehearsal) and 5 (rate limit). Ramon says the **real connector service is now running on the Mac Studio** (`10.0.0.8:8083`; installed as a background service, funder stage only). Two checks could not be judged while it was down.

## Checks
1. **Reachability first:** a connect-only test to `10.0.0.8:8083` from this host (open / refused / timed out), and `https://mcp.digitaldemocracyproject.org/`: the status code. Expect **401 or a protocol error, not 502**. If it is still 502 or refused, stop and say so; do not retry in a loop.
2. **Streaming and first-byte timing:** one request to the `mcp` address, same as your earlier check 1. Report the status, the time to first byte and the total time. A first byte that arrives only at the very end of a long request would suggest buffering; with a plain GET there is little to judge, so say if the result is inconclusive.
3. **The other sites once more:** `api /health`, `http://votebot.../`, `https://dev.../` status codes, and the count of new `connect() failed` lines for the `mcp` name since this note was posted (should be zero from the moment the service started; say when it started if the log shows it).
4. **Rate limit still sane with real traffic:** the count of 429 responses for the `mcp` name since the limit went on, other than your own burst test.

## Report
A short table: check, result, anything unexpected, and which you did not run and why.
