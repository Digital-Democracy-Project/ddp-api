# Request: is the Mac Studio still reachable from the civic host over WireGuard after its new firewall rule? (AGENTS-210, epic AGENTS-203)

For the prod agent of the civic host. Posted by Agent Smith at Ramon's request, 2026-11-04. **Read-only: connection tests and web requests only. Change nothing on this host.**

## What changed on the Mac Studio
At about 04:25 UTC Ramon (admin, on the Mac Studio) installed a macOS firewall (`pf`) rule that affects **only inbound TCP to port 8083** on the Mac: the Mac itself and this host (`10.0.0.1`) may connect, every other source is blocked. Port 8083 is the grants connector's port; nothing else uses it. Nothing else about the firewall is meant to change. pf may have been switched on for the first time by this (it was likely off before), so we want proof that nothing else on the Mac became unreachable. If anything below is worse than your earlier Step 0 readings, tell Ramon at once: he can remove the rule in one command.

## Checks, from this host, and what we expect (compare with your Step 0: WireGuard handshake under 2 minutes, `ping 10.0.0.8` 2 of 2 at about 20 ms, `10.0.0.8:8083` refused)
1. WireGuard: the Mac peer's latest handshake age (`wg show`, no keys in the note) and `ping -c 4 10.0.0.8`. Expect the same as before.
2. TCP connect tests with a short timeout (connect only, send nothing) to the Mac at `10.0.0.8` on: `3000` (what `dev` proxies to), `8000`, `8002`, `8080`, `8081`. Expect each to connect as it did before the rule. Report each as **open**, **refused** or **timed out**. A *timed out* where it used to connect is the failure we are looking for.
3. `10.0.0.8:8083` from this host: expect **refused** (the connector is not running yet). **Refused is the good answer** (it means this host gets through the firewall to a port with nothing listening). **Timed out would mean the rule blocks this host**: report it and tell Ramon.
4. Web: `https://dev.digitaldemocracyproject.org/`, `https://api.digitaldemocracyproject.org/health`, `http://votebot.digitaldemocracyproject.org/` status codes (expect 200 as before), and `https://mcp.digitaldemocracyproject.org/` (expect 502, certificate verifies).
5. If you can see it without touching anything: whether any service on this host logged connection errors to `10.0.0.8` since 04:25 UTC (counts only, no content).

## Report
A short table of the results (open/refused/timed out and status codes), what is different from Step 0, and whether anything looks wrong. No keys, tokens or public IP addresses in the note. Post it on this branch.

## If something is wrong
Do not change anything on the Mac (you cannot see it anyway). Say which port or check failed; Ramon removes the rule with `sudo bash <script> --undo` on the Mac.
