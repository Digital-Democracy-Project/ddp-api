# Request: read-only check of why `/votebot/chat` and friends return 404 on the public URL (dev agent, on Ramon's instruction, 2026-10-07 evening)

From the dev agent (Claude Code, ddp-api repo). Everything below is read-only; nothing changes on the host, and no key is needed except where noted (do not paste any key).

## What I found

At about 00:36 UTC on 2026-10-08 I ran every "Try it out" button on the live `https://api.digitaldemocracyproject.org/docs` in a browser with a read-only key (53 buttons, all of them executed). Two of them, **`POST /votebot/chat` and `POST /votebot/chat/stream`, return `404 {"detail":"Not Found"}`**. Plain `curl` shows the same, **with or without a key**:

| Request to the public host | Result |
|---|---|
| `POST /votebot/chat` (no key) | 404 `{"detail":"Not Found"}` |
| `POST /votebot/feedback` (no key; a write route) | 404 |
| `POST /get_users` (no key; a read route that ddp-api itself serves) | **401** (ddp-api's own auth answered) |
| `GET /votebot/chat/stream`, `/votebot/ws`, `/votebot/health` | 404 |
| `GET /votebot/v1/chat` | **405** with `allow: POST` (so a real VoteBot route) |
| `GET /votebot/v1/health` | **200** `{"status":"healthy","version":"2.0.0","environment":"development",...}` |

A route that ddp-api serves answers 401 without a key; `/votebot/chat` answers 404 without one. So I believe ddp-api never sees requests under `/votebot/` on the public host, and something in front of it (nginx is my guess; the `Server:` header says `nginx/1.18.0`) hands them to VoteBot, whose own paths are `/votebot/v1/...`. That would make ddp-api's own `/votebot/chat`, `/votebot/chat/stream`, `/votebot/feedback` and `/votebot/ws` unreachable on the public URL even though they are in ddp-api's code and on its `/docs` page. I cannot see the nginx config, so this is a hypothesis; the points below are what would settle it.

## Questions (read-only)

1. **What matches `/votebot/`?** Which nginx `location` block(s) handle `/votebot/` (and `/votebot/v1/`, if separate) on this host, and what do they forward to (host and port only)? Quote the block, with nothing secret in it. If the config is in git, when did that block last change?
2. **Does ddp-api itself serve the route when nginx is bypassed?** On the host, `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/votebot/chat` (a GET, no key, no body, so it does not call VoteBot). Expect **405** (route exists, wrong method) or **401** if ddp-api's auth runs first. A **404** would mean ddp-api does not have the route at all. I am deliberately not asking you to POST a chat.
3. **Is anyone using the public `/votebot/*` paths?** From the nginx access log, counts only, for the last 7 days (or as far back as the log goes): requests to `/votebot/v1/chat`, `/votebot/chat`, `/votebot/chat/stream`, `/votebot/feedback`, and `/votebot/ws`. If you can see the client (for example ddp-next), say which paths it calls and not the requesters' addresses.
4. **VoteBot's reported environment.** `/votebot/v1/health` on the public host says `"environment":"development"`. Is VoteBot here configured as `development` on purpose, or is that the public path reaching a dev-configured instance? Just report; nothing to change.
5. **Two smaller confirmations while you are there.** (a) `GET /broker/api/search/` returns **503** `{"detail":"search is temporarily unavailable"}` through ddp-api; is that the expected state with search off in production? (b) Nothing else to check.

## What this is NOT

- Not a request to change nginx, ddp-api or VoteBot. Whether the right fix is to correct the routing or to stop listing those four routes on the docs page is Ramon's decision, and it depends on your answers to 1 and 3.
- Not an outage that I can see: VoteBot itself answers on `/votebot/v1/*`.

## Also seen in the same pass (no ops action)

- Four broker routes (`bill-artifacts/status`, `bill-organization-positions/current`, `bill-organization-positions/status`, `concept-statements/status`) return 400 from the docs page because the broker's schema does not declare the parameters they need. That belongs to ddp-broker-py's schema, not to the host.
- `/get_tokens`, `/get_users`, `/get_events` return HTTP 200 with a structured `{"status":"error",...}` for failures, by design; read them accordingly.
- Everything else (45 GETs, the Webflow checks, `/user_updates` with its placeholder tokens) behaved as expected.

Reply on this branch either way. Nothing here blocks anything.
