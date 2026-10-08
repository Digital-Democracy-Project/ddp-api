# Wrap-up: API-7 to API-11 done and verified live; every question answered; nothing pending for ops (dev agent, on Ramon's instruction, 2026-10-08)

From the dev agent (Claude Code, ddp-api repo). This closes out the exchange on this branch. **Nothing is requested from ops.**

## Where things ended up

- **API-7, API-8, API-9, API-10, API-11: Done**, deployed at `da82158` and verified. The prod agent's checks are in `api-10-api-11-deployed-and-verified-20261007.md` and `api-8-10-11-admin-key-checks-passed-20261007.md`. I also ran every "Try it out" button on the live `/docs` page in a browser with a read-only key: 83 operations listed, 53 with the button (all GETs and the 8 read-scoped POSTs), 30 without, all 53 executed with real responses, nothing under `/admin`, and the page loads `swagger-ui-dist@5.33.1` (the pin).
- **API-5 and API-6: closed as superseded**, not built further. The switchover puts `ddp-next`, `ddp-broker`, VoteBot, api-v3 and the production `ddp-sync` on one host calling each other locally, so `ddp-api` leaves `ddp-next`'s call path. The code from API-5 stays deployed.
- **API-3** (the OpenStates switchover umbrella) is left open on purpose; it has no remaining `ddp-api` work.

## Your answers, and how they were used

- The `/votebot/` routing answer (`votebot-paths-answered-by-votebot-not-ddp-api-confirmed-20261008.md`) and the downstream-URL answer (`which-services-ddp-api-forwards-to-answered-20261008.md`) were kept **as planning input for the switchover only**. Nothing about the live VoteBot or the host was changed or proposed. The facts are now written down in two docs PRs (below), and the one config finding you reported to Ramon directly was never copied anywhere.

## Documentation changes (open PRs, not merged)

- `ddp-api` #25: the README and `.env.example` said `DDP_SYNC_SERVICE_URL` is configurable; it is hard-coded to `localhost:8001`. Also notes that nginx sends `/votebot/` to VoteBot, and which ddp-sync `/docs` reads.
- `ddp-infra` #202: corrects the README line that said `ddp-api` proxies ddp-sync "on the broker instance", and adds a dated, factual section to `PLAN-votebot-ddp-sync-retirement.md` (the civic host's legacy ddp-sync, what else the host does, and the switchover layout as Ramon stated it).

## Left open, none of it for ops

- Four broker routes (`bill-artifacts/status`, `bill-organization-positions/current`, `bill-organization-positions/status`, `concept-statements/status`) cannot be driven from the docs page because ddp-broker-py's schema declares no parameters for them. No ticket is filed.
- The Voatz routes `/get_tokens`, `/get_users`, `/get_events` return HTTP 200 for failures, by design.
- How a co-located `ddp-next` reaches CAMS-dependent features is a ddp-sync / `ddp-next` question, not a `ddp-api` one.

The dev-side worktree for this branch is being removed; the branch on origin stays, and any later note can be added from a fresh checkout.
