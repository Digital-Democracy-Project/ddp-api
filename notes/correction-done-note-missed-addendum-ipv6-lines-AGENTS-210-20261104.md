> **Correction to** `done-grants-mcp-nginx-site-and-certificate-AGENTS-210-20261104.md` (AGENTS-210, epic AGENTS-203). Posted on **this** branch (ddp-api `notes/ops-handoff`). **Nothing was changed on the host for this note.** No key, secret or public IP address is in it.

# I did not read `addendum-grants-mcp-nginx-protect-api-votebot-20261104.md` before doing the work; the file does not follow it on one point

The addendum was on the branch when I pushed the done-note. I had not pulled it before running reload 1, the certificate and reload 2, and I wrote the done-note without reading it. Found and checked afterwards.

## Where the live file differs from the addendum
- **IPv6 `listen` lines (addendum point 1):** the file has `listen [::]:80;` (port-80 block) and `listen [::]:443 ssl;` (443 block). `api` has no `[::]:443` line, so per the addendum both should be omitted.
- **Effect today:** `[::]:443` is a **new listening socket** (it did not exist before this change), and `mcp` is the only server on it, so an IPv6 https request to any name on this host would be answered with the `mcp` certificate, not `api`'s. This host has no global IPv6 address and neither `api.` nor `mcp.` has an AAAA record, so nothing reaches it now. `[::]:80` was already open (the default site listens on it), so the port-80 line adds no new socket.

## Addendum point 2 (before/after check on `api` and `votebot`): done only after the fact
I did not record a before-state for `api`. Current state, read-only: an https request for an unknown name is answered with the `api` certificate (`api` sorts first in `sites-enabled`, the new file sorts after `api` and `dev`), the `api` name gets the same certificate, `https://api.../health` returns `200`, and the VoteBot site answers `200`. Nothing suggests `api` or `votebot` changed; the only gap is that I have no earlier reading to compare with.

## The other "Also" items: followed
Only `server` blocks in the file, no `http`-level directive or `upstream`; `certbot certonly` with the nginx plugin (no file other than the new one was touched); no other file edited; ddp-sync and votebot untouched; no package or token installed.

## To fix the IPv6 lines
Remove the three IPv6 `listen` lines (two in the port-80 block, one in the 443 block), `nginx -t`, reload. **That is a third reload, beyond Ramon's two.** Not done: waiting for Ramon's yes.
