> **Report for the dev agent** (found while checking `api.` and `votebot` after the AGENTS-210 nginx work). Posted on **this** branch (ddp-api `notes/ops-handoff`). **Read-only investigation, stopped early on request. Nothing was changed on the host for this note.** No key, secret or public IP address is in it.

# `GET https://api.digitaldemocracyproject.org/votebot/ws` with a WebSocket handshake returns 404 on the api host

## What I saw
- An unauthenticated WebSocket upgrade handshake (curl, with the `Upgrade: websocket` headers) to `https://api.digitaldemocracyproject.org/votebot/ws` returned **404**, 22 bytes, once. The access log shows that one line only, from my own curl. No real client request for `/votebot/ws` appears in the current or rotated log, so there is **no evidence of real traffic or of a real failure**.
- This is **not caused by the AGENTS-210 work**: the `api` site file was not edited, and `api` and `dev` sort ahead of the new `mcp` file.

## What the config says (read, not tested)
`/etc/nginx/sites-available/api.digitaldemocracyproject.org` has these locations:

| Location | Upstream | Upgrade headers |
|---|---|---|
| `/votebot/sync` | `127.0.0.1:5000` (DDP-API) | no |
| `/votebot/trigger` | `127.0.0.1:5000` | no |
| `/votebot/` | `127.0.0.1:8000` (VoteBot service) | no |
| `/` | `127.0.0.1:5000` | no |
| `/ws/chat` | `127.0.0.1:8000` | **yes** |

- There is **no `/votebot/ws` location** on the api host. A request for `/votebot/ws` matches `location /votebot/` and goes to **VoteBot on :8000, without WebSocket upgrade headers**. A 22-byte 404 is the size of a FastAPI `{"detail":"Not Found"}`, so it is likely VoteBot's own 404 (inference, not confirmed).
- DDP-API itself defines `@router.websocket("/ws")` in `app/routes/votebot.py` (line 160; I did not check the router's prefix, so I assume the public path is `/votebot/ws`). It proxies on to VoteBot's `ws://localhost:8000/ws/chat`.
- The **default** nginx site (the catch-all for other host names) does have a `location /votebot/ws` to `127.0.0.1:5000` with upgrade headers. So DDP-API's `/votebot/ws` is reachable through the default site but, as far as the config shows, **not through the `api.` host**; on `api.` the working WebSocket path is `/ws/chat` straight to VoteBot.

## What I did not check
- I did not call `127.0.0.1:5000/votebot/ws` directly to see whether the app answers the handshake (that call was declined), so I cannot say what the app itself returns.
- I did not test with a real WebSocket client, or with a valid key.
- I did not read the existing notes `request-read-only-votebot-paths-answered-by-votebot-not-ddp-api-20261007.md` and `votebot-paths-answered-by-votebot-not-ddp-api-confirmed-20261008.md`; their names suggest this routing split may already be known and documented.

## Question for the dev agent
Is the intended public WebSocket entry point `/ws/chat` (straight to VoteBot) or DDP-API's `/votebot/ws`? If it is `/votebot/ws` on the `api.` host, nginx there needs a `location /votebot/ws` (to `:5000`, with the upgrade headers) placed before `location /votebot/`; if it is `/ws/chat`, the 404 is expected and the README/docs may just need to say so. I have not changed anything and will not edit the `api` site without an instruction on this branch.
