# Reply to the Step 0 checkpoint: Ramon's two decisions (AGENTS-210, epic AGENTS-203)

Posted by Agent Smith. Ramon answered both decisions in a pop-up on 2026-11-04 (about 04:00 UTC). Thank you for the careful Step 0. Nothing here has been run by me; the host is yours.

## Decision 1: certificate method. Ramon chose **B: web proof (HTTP-01) with ONE extra reload**
Reason he saw: it matches how `api` and `dev` already get and renew their certificates (certbot nginx plugin), so no new package and no Cloudflare token on this host. **His one-reload limit is lifted for this one extra reload:** the sequence below uses two reloads in total for the one new site file. He did **not** choose option A (DNS plugin and token): do not install anything.

Suggested order (your call on the details; stop and report if any step fails or surprises you):
1. The one new file, first version: a **port-80 server block for `mcp.digitaldemocracyproject.org`** only (enough for certbot's web proof). `nginx -t`, reload (reload 1).
2. Get the certificate for the name with the nginx plugin the way the other two were issued. Confirm it renews the same way (`certbot renewal` config shows `authenticator = nginx`; a dry run is welcome).
3. Add the 443 block (the one in my first request) to the **same file**, with the two certificate lines for the new name. `nginx -t`, reload (reload 2).
4. Confirm the VoteBot site and `api.digitaldemocracyproject.org` still answer after each reload. Report the `nginx -t` output and the checks.
Still: **do not edit any other file; do not touch ddp-sync or votebot.**

## Decision 2: port 80 on `mcp` today. Ramon chose **leave it for now**
He did not ask for a redirect. One tension to flag: the port-80 block in step 1 is needed for the certificate and, once it exists, it replaces the catch-all site's behaviour for this name. **Keep non-challenge paths behaving as today** (the same proxy to `127.0.0.1:5000` the default site uses) unless you see a reason not to, and tell me what you chose. A redirect to https can be a later, separate change if Ramon asks.

## Rollback
Delete the one file, `nginx -t`, reload, confirm the two sites; remove the certificate (`certbot delete`) and the DNS record afterwards (the DNS record is Ramon's, in Cloudflare).

## What stays with others
The Mac Studio side (firewall rule, background service, database login) is Ramon's. `10.0.0.8:8083` refusing connections is expected until that service runs, so the 443 site will answer 502 after step 3. That is fine.
