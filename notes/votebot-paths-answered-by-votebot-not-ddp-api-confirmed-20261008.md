# Answer: `/votebot/chat` and friends 404 on the public URL — confirmed, nginx sends `/votebot/` to VoteBot (ops session, 2026-10-08)

From the ddp-api session (Claude Code, on the ddp-api host), answering `notes/request-read-only-votebot-paths-answered-by-votebot-not-ddp-api-20261007.md`. Everything below was read-only: no config, service or data changed, no key printed. The only authenticated call was one `GET` (question 5a), using the host's env-var token from `.env`.

## Your hypothesis is correct

### 1. What matches `/votebot/`

`/etc/nginx/sites-enabled/api.digitaldemocracyproject.org` (a symlink to `sites-available/`, file last modified 2026-03-11; `/etc/nginx` is not in git) has these `location` blocks, in this order:

| Block | Forwards to |
|---|---|
| `location /votebot/sync` | `http://127.0.0.1:5000` (ddp-api), `proxy_read_timeout 120` |
| `location /votebot/trigger` | `http://127.0.0.1:5000` (ddp-api), `proxy_read_timeout 300` |
| `location /votebot/` | **`http://127.0.0.1:8000` (VoteBot)** |
| `location /` | `http://127.0.0.1:5000` (ddp-api) |
| `location /ws/chat` | `http://127.0.0.1:8000` (VoteBot), websocket upgrade headers, `proxy_read_timeout 86400` |

`/votebot/v1/...` is not a separate block; it is caught by `location /votebot/`. So every path under `/votebot/` except `/votebot/sync*` and `/votebot/trigger*` goes to VoteBot, and ddp-api never sees it. Those two exceptions look like leftovers: ddp-api has no `/votebot/sync` or `/votebot/trigger` route (its sync/trigger proxies are `/sync/*` and `/trigger/*`).

This also explains the repo README's nginx sample: it shows only `/votebot/ws`, which is not what is deployed.

### 2. Does ddp-api serve the routes when nginx is bypassed?

Yes, except the websocket (which a plain GET would not exercise). GET with no key, no body, straight to `127.0.0.1:5000`:

| Path | Status |
|---|---|
| `/votebot/chat` | 405 |
| `/votebot/chat/stream` | 405 |
| `/votebot/feedback` | 405 |
| `/votebot/ws` | 404 (a plain GET against a websocket-only route; not conclusive) |

405 means the route exists and wants POST. Also `GET http://127.0.0.1:8000/votebot/v1/health` returns 200, so VoteBot answers those paths directly.

### 3. Anyone using the public `/votebot/*` paths?

nginx access logs, 2026-10-01 through 2026-10-08 01:20 UTC (about 7 days). Counts only, no addresses.

| Path | Requests | Status |
|---|---|---|
| `/votebot/v1/features` (GET) | about 6,730 | 200 (4 are 499) |
| `/votebot/v1/content/resolve` (GET) | 10 | 7 x 200, 3 x 400 |
| `/votebot/v1/chat` | 2 | `HEAD`/`GET`, both 405 (not a chat) |
| **POST `/votebot/v1/chat`** (and `/chat/stream`) | **0** | — |
| `/votebot/chat` (POST) | 6 | all 404 |
| `/votebot/chat/stream` (POST 3, GET 1) | 4 | all 404 |
| `/votebot/feedback` (POST) | 1 | 404 |
| `/votebot/ws` (GET) | 1 | 404 |
| `/votebot/health` (GET) | 1 | 404 |
| `/votebot/v1/health` (GET) | 1 | 200 |
| `/ws/chat` | about 11,826 | 11,815 x 101 (websocket connected), 8 x 404, 3 x 499 |

Reading it:

- The `/votebot/features` traffic is a browser widget: user agents are ordinary Windows/Mac browsers plus crawlers (Baiduspider, DuckDuckBot). That is the embedded chat widget loading its feature flags on page views.
- Live chat goes over **`/ws/chat`** (websocket, 101), straight to VoteBot, not through ddp-api.
- The 404 hits on `/votebot/chat`, `/chat/stream`, `/feedback`, `/ws` and `/health` (13 in total) have no consumer that I can identify; they are most plausibly your own browser pass and `curl` probes from 2026-10-08 (00:36 UTC), though I did not check timestamps against it.
- **No one POSTs a chat message to `/votebot/v1/chat` over the public URL in this window.** I can only see this host's nginx log, so a client that reaches VoteBot another way (for example directly on its own host or VPC) would not show up.
- I did not identify ddp-next as a caller of any path; only `python-httpx/0.28.1` (3 hits) on `/votebot/v1/content/resolve` looks like a server client.

### 4. VoteBot's reported environment

`/home/ubuntu/votebot/.env` sets `ENVIRONMENT=development`. So `/votebot/v1/health` reporting `"environment":"development"` reflects that setting on this instance, and nothing indicates it was chosen deliberately for production; whether that is intended is for Ramon to say. That one VoteBot (:8000) is what the public paths reach. I did not look at what that value changes inside VoteBot.

### 5. Smaller confirmations

- **(a) `GET /broker/api/search/`:** 503 `{"detail":"search is temporarily unavailable"}` again when called from the host against ddp-api (`127.0.0.1:5000`). I only reproduced it; I did not check the broker's own configuration, so I cannot confirm whether "search off in production" is intended.
- **(b)** Nothing else checked.

## What this means for the decision (Ramon's, not made here)

- ddp-api's `/votebot/chat`, `/votebot/chat/stream`, `/votebot/feedback` and `/votebot/ws` exist in code and on `/docs` but are **unreachable through the public host**, because `location /votebot/` shadows them. They work on `127.0.0.1:5000`.
- Nothing in the logs depends on them being reachable: zero legitimate requests, and the real chat path (`/ws/chat`, `/votebot/v1/*`) bypasses ddp-api entirely.
- The two options are the ones you listed: fix the routing (for example a more specific nginx `location` for those four paths, which would have to be tried against the widget's traffic on `/votebot/v1/*` and `/ws/chat`), or stop listing those four routes on `/docs`. This is a choice about what ddp-api's public surface should be, so I have not touched either.

## Also noticed (no action taken)

- `/etc/nginx/sites-enabled/votebot` is a regular file, not a symlink like the other three, and its `server_name` is `votebot.digitaldemocracyproject.org`; I only grepped it and did not read it in full.
- `/etc/nginx` is not under version control, so there is no history for question 1's "when did that block last change"; the file's mtime (2026-03-11) is the only evidence.

Nothing here blocks anything.
