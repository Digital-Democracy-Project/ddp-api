# Steps 1-2 confirmed done -- all three handoff steps now complete

Following up on `notes/openstates-proxy-pr15-merged-please-restart-and-verify-20260915.md` and
`notes/votebot-key-minted-step3-done-20260915.md`.

PR #15 is now actually merged to `main` (`d1cab0f`, confirmed via `git fetch` + `merge-base
--is-ancestor`) -- it wasn't yet at the time the first note was written. Local `main` has been
fast-forwarded to match.

## Step 1: restart -- done

```
sudo systemctl restart ddp-api
```

Confirmed via `systemctl status`: new process came up clean (fresh PID), no crash on startup,
picked up `.env`'s `OPENSTATES_SERVICE_URL` and `OPENSTATES_PROXY_KEY` (both already set in the
real `ddp-api/.env` per the first note).

## Step 2: smoke test -- done, 200

```
curl -s https://api.digitaldemocracyproject.org/openstates/jurisdictions \
  -H "Authorization: Bearer $DDP_API_READ_TOKEN"
```

Result: **HTTP 200**, real jurisdiction data returned (e.g. Adrian MI, Alabama, ...). Confirms
`OPENSTATES_SERVICE_URL` and `OPENSTATES_PROXY_KEY` are correct together, and the key is
registered in the target instance's own `profiles_profile` table.

## Step 3 (for reference, already reported done)

VoteBot's read-only key exists (`name: "VoteBot OpenStates replica"`, `scopes: ["read"]`,
`restrictions.endpoints: ["/openstates"]`) -- see `/admin/keys` for the id. Plaintext already
handed off to `votebot`'s own `.env` per that note.

All three steps in the original handoff are now complete. VOTEBOT-2 should be unblocked to flip
on `USE_DDP_OPENSTATES_REPLICA`.
