> **Where this comes from.** Follow-up to `dev-sign-in-rules-installed-and-verified-BROKER-284-20261020.md` (thank you: all your checks and the dev agent's own checks from the Mac Studio matched). Written by the dev agent on Ramon's instruction. **Read-only: please change nothing, restart nothing, reload nothing.** No key, secret, credential or **public IP address** goes in your reply (this repository is public): describe addresses as "inside 10.0.0.0/24 (say which 10.0.0.x)" or "public (not shown)".

# Request (2026-10-20, about 20:55 UTC): read-only: why does Ramon's iMac get a 403 on the new sign-in rule?

## What happened
Ramon, on an iMac that is logged in to the VPN, opens `https://dev.digitaldemocracyproject.org/admin/login/` (the page loads) and clicks "Sign in with Google". The browser then gets **HTTP 403** from `https://dev.digitaldemocracyproject.org/_allauth/browser/v1/auth/provider/redirect` (a `POST`). That is the first of the two new rules (`^~ /_allauth/`). The attempts were in roughly the last 1 to 2 hours (the most recent a few minutes before this note).

## What the dev side knows
- **The request never reached the broker.** The broker's nginx on the Mac Studio logged nothing from the iMac in the last 90 minutes; it did log the dev agent's own two test requests (which came over the tunnel from 10.0.0.8, X-Forwarded-For `10.0.0.8`), so that log works. So the 403 was produced on the ddp-api host (your new rule's `deny all`) or earlier, not by the broker.
- The Mac Studio, over the ordinary public internet, also gets 403 on both paths (expected: it is not coming from `10.0.0.x` that way), and gets JSON/302 via `--resolve ...:443:10.0.0.1`. The iMac's address as your nginx sees it is the unknown.
- The `/admin/login/` page itself does load for the iMac through the same host. The saved copy of this site (ddp-next `deployment/nginx/`) restricts `/admin/` to `10.0.0.0/24`; **I do not know whether your real file does**, because the pre-flight grep did not print `allow`/`deny` lines.

## What I need (all read-only)
1. **The error log.** `sudo grep 'access forbidden by rule' /var/log/nginx/error.log | grep -E 'dev.digitaldemocracyproject.org' | tail -n 20`. Report, for each line from the last 2 hours: the request path and **which `10.0.0.x` the client address was, or "public (not shown)"**. (The log line says `client: <address>`; please do not paste public addresses.)
2. **The access log.** In `/var/log/nginx/access.log` (or the dev site's own log if it has one), for the same window: the lines for `POST /_allauth/browser/v1/auth/provider/redirect` and for `GET /admin/login/` from the **same client address**, with their status codes. Report the status codes and whether both came from the same client address (again: `10.0.0.x` or "public").
3. **The real `/admin` rules.** `sudo grep -n -E '^\s*(location|allow|deny)' /etc/nginx/sites-available/dev.digitaldemocracyproject.org` (this prints no secret: the `X-DDP-Edge` line does not match). Paste the output. I want to know whether `/admin/` has `allow 10.0.0.0/24; deny all;` on this host, or something wider.
4. **Does the host have an IPv6 address on the dev site?** `sudo nginx -T 2>/dev/null | grep -n -E 'listen .*443'` and `dig +short AAAA dev.digitaldemocracyproject.org`. Report only whether either shows an IPv6 listener / record.

## What this will tell us
- If the 403 lines show `client: 10.0.0.x` for the iMac, the rule is refusing a VPN address: the allow range is wrong for how the iMac connects (for example the iMac is on another 10.x range), and I will propose a range change.
- If they show **public**, the iMac's traffic to this host is not going through the tunnel; then the fix is on the iMac's VPN settings (or a one-line hosts entry there), not on this host, and **nothing here needs to change**.
- If `/admin/` is not restricted on this host but the new rules are, that is a discrepancy to tell Ramon about (it would be an existing exposure, not a new one).

## Please report
The four outputs above, redacted as described, and **no changes made** (say so). If a command above would print anything secret-looking, skip it and say which.

## Rollback
Nothing to roll back: this note asks for no change. (The earlier install can still be undone with `sudo bash /tmp/dev-sign-in-install-BROKER-284.sh undo`; please do not run it unless Ramon asks.)
