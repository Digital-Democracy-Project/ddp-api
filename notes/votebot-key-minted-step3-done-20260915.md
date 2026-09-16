# Step 3 done -- VoteBot's key minted; Steps 1-2 still unconfirmed

Ramon ran Step 3's curl from `notes/openstates-proxy-pr15-merged-please-restart-and-verify-20260915.md`
directly. VoteBot's read-scoped key (`"name": "VoteBot OpenStates replica"`, `scopes: ["read"]`,
restricted to `/openstates`) is minted. The plaintext is going into `votebot`'s own `.env` as
`DDP_OPENSTATES_BEARER_TOKEN` (separate repo/host, tracked on VOTEBOT-2) -- nothing further
needed here for that part.

**Steps 1 and 2 from that note are still open as far as this branch shows**: no confirmation yet
that `ddp-api` was actually restarted (`sudo systemctl restart ddp-api`) to pick up
`OPENSTATES_SERVICE_URL`/`OPENSTATES_PROXY_KEY` from PR #15, and no reported result from the
`/openstates/jurisdictions` smoke-test curl. Please don't assume Step 3 succeeding implies those
two are also done -- they're independent (Step 3 only proves the `ddp-api`-issued bearer token
exists; it says nothing about whether the *internal* forwarding key to api-v3 is live). If you've
already done the restart and smoke test, reply here with the actual result (200/401 and which);
if not, those are still the real blockers on VOTEBOT-2.
