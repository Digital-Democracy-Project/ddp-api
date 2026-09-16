# ddp-api side fully confirmed -- next: deploy and verify votebot itself

Following up on `notes/openstates-proxy-restart-and-smoke-test-confirmed-20260916.md`. All three
original handoff steps (restart, smoke test, VoteBot key mint) are done -- thanks. The last
remaining piece for VOTEBOT-2 is entirely on the `votebot` side, a separate repo/host from
everything above.

`votebot` PR #6 (routes the three OpenStates call sites through this proxy behind a flag) is
merged to `votebot`'s `main`. Nothing has been deployed yet as far as any note on this branch
shows.

## Step 1: deploy

On the VoteBot EC2 host:

```bash
cd /path/to/votebot   # wherever the real checkout lives
git pull origin main
```

Then set these three vars together in the real `votebot/.env` (not `.env.example`) -- all three
are required, none of them do anything alone:

```bash
USE_DDP_OPENSTATES_REPLICA=true
DDP_OPENSTATES_API_ROOT=https://api.digitaldemocracyproject.org/openstates
DDP_OPENSTATES_BEARER_TOKEN=<the plaintext from the already-minted "VoteBot OpenStates replica" key>
```

Restart:

```bash
sudo systemctl restart votebot
sudo systemctl status votebot
```

## Step 2: verify via VoteBot's own health check

```bash
curl -s http://localhost:8000/votebot/v1/health/ready | python3 -m json.tool
```

Confirm `dependencies.ddp_openstates_replica` reads `"healthy"` (this checks the proxy's
`/openstates/healthz` passthrough end-to-end -- it will read `"unhealthy"`/be entirely absent if
the flag isn't actually on, or if VoteBot can't reach `api.digitaldemocracyproject.org` for some
reason).

## Step 3: one real functional check, not just health

Trigger a real bill-vote lookup through VoteBot (chat message asking about a specific bill's
vote, or however this is normally exercised) and confirm it returns real data with no errors --
ideally something you can cross-check for DDP's own corrections actually showing up (this
routing change exists specifically so DDP's scraper fixes are reflected, not just openstates.org's
raw data), not just "didn't crash."

Report back: git pull confirmed on the right commit, restart clean, Step 2's actual JSON, and
Step 3's result. Once that's real and confirmed, VOTEBOT-2 can close.
