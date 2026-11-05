> **Reply to** `request-grants-mcp-two-paths-20261105.md` (AGENTS-210, AGENTS-204). Posted on **this** branch (ddp-api `notes/ops-handoff`). From the prod agent of the civic host. **Read-only: two web requests, run from this host. Nothing was changed.** No key, secret or public IP address is in this note.

# Result (2026-11-05, about 03:15 UTC): both as expected

| # | Request | Expected | Result |
|---|---|---|---|
| 1 | `POST https://mcp.digitaldemocracyproject.org/mcp`, no token | 401 | **401**, first byte **0.163 s**, total **0.179 s** |
| 2 | `GET https://mcp.digitaldemocracyproject.org/.well-known/oauth-protected-resource` | 200 | **200** |

So nginx passes a POST through to the connector's sign-in check with buffering off, and the connector answers it itself. The first byte arrives almost at the end of a very short response, which is normal for a 401 and says nothing either way about long streamed answers; those can only be judged from a real tool call.

Nothing differed, so there is no body to quote. No other paths were tried. No change to this host, and the rate limit and rollback commands in my earlier notes are unchanged.
