> **Where this comes from.** BROKER-284 (https://digitaldemocracyproject.atlassian.net/browse/BROKER-284), ddp-broker-py PR #491 (merged). Written by the dev agent on Ramon's instruction. The dev machine has no SSH to this host, on purpose, so **you run everything below on the host**. Reply on **either** this branch or ddp-broker-py's `notes/ops-handoff`, and say which. No key, secret or credential is in this note, and none should go into your reply (this repository is public).

# Request (2026-10-20): add two sign-in rules to the `dev.digitaldemocracyproject.org` nginx site, check them, report

## Why
Staff can now sign in to the broker's Django admin with their Google Workspace account (BROKER-283, merged and running on the Mac Studio dev broker; a real sign-in was done on 2026-10-20 through a temporary hosts-file line). On the real dev address it cannot work yet, because of how a request travels today:

`browser -> this host's nginx (dev.digitaldemocracyproject.org, TLS ends here) -> ddp-next on the Mac Studio (10.0.0.8:3000) -> only /admin and /static are passed on to the broker`.

Google's sign-in also needs `/_allauth/` (start the sign-in) and `/accounts/` (the address Google sends the browser back to) to reach the broker, and the **hostname must arrive unchanged** (Google builds its return address from it). Ramon decided: fix it **here, not in ddp-next** (other people are working in that repo), and **VPN-only for now** (same rule as `/admin`).

## What the change is (and is not)
Three things on this host, all nginx:
1. **One new file** `/etc/nginx/conf.d/ddp-broker-sign-in-zone.conf` with one line: `limit_req_zone $binary_remote_addr zone=broker_sign_in:10m rate=10r/s;` (a rate limit; it must be at the http level, and `conf.d` is the place that is already included there).
2. **One new file** `/etc/nginx/snippets/ddp-broker-sign-in.conf` with two `location ^~` blocks, `/_allauth/` and `/accounts/`. Each: `allow 10.0.0.0/24; deny all;`, the rate limit (burst 20, answers 429), `proxy_pass https://10.0.0.8;` (the Mac Studio's broker nginx, inside the tunnel; its certificate is self-signed and nginx does not check an upstream certificate unless told to), `Host $host` and `X-Forwarded-Proto $scheme` kept.
3. **One added line** inside the `listen 443 ssl` server block of `/etc/nginx/sites-available/dev.digitaldemocracyproject.org`: `include /etc/nginx/snippets/ddp-broker-sign-in.conf;`, right after the `listen` line.

**Not changed:** the `/admin/`, `/static/` and `/` blocks, the edge secret, certificates, any other site (`api.*`, `votebot`, ...), ddp-api, ddp-sync, anything on the broker host (10.0.0.11), or ddp-next. No restart: a **reload** only. The same nginx serves `api.digitaldemocracyproject.org`, so nothing is reloaded unless `nginx -t` passes first.

The rules are exactly the ones in ddp-broker-py `infra/front-door/dev-sign-in.conf` (merged in #491), and the script below was checked to contain them unchanged.

## What I tested, and what I could not
**Tested** (on a throwaway Debian nginx with a copy of the saved site file from ddp-next `deployment/nginx/dev.digitaldemocracyproject.org`): install puts the include line right after `listen 443 ssl` and changes nothing else in the file; the live server then answers 403 to a non-VPN address on both paths and leaves `/admin/` as it was; a second install changes nothing; undo gives back a byte-for-byte identical site file; the script stops without touching anything if there is not exactly one `listen 443 ssl`, if `conf.d` is not included, or if nginx is already failing; and if nginx rejects the result (I forced a clash on the zone name) it restores the original file and removes its new files.
**Could not test:** your real site file (I only have the saved copy; I do not know how it differs now), the real certificate, the real tunnel, and the real Google click-through. **That is why step 1 is a read-only look first.**

## Steps (you run everything on the host)

**Step 1: read-only pre-flight. Change nothing. If anything differs from "expect", STOP and report it; do not go on to step 2.**
- `ls -l /etc/nginx/sites-enabled/` and confirm `dev.digitaldemocracyproject.org` is there and enabled. *Expect:* present (a symlink to `sites-available/`, like `api.*`). If this host has no such site, stop: the plan assumes it does.
- `sudo grep -n -E 'server_name|listen|location|include|ssl_certificate' /etc/nginx/sites-available/dev.digitaldemocracyproject.org`. *Expect:* exactly **one** `listen 443 ssl`; `location` blocks for `/admin/`, `= /admin`, `/static/` and `/` (the saved copy has these; yours may have more). **Paste the output of this command into your reply** (it contains no secrets; do **not** paste the `X-DDP-Edge` line).
- `sudo nginx -t`. *Expect:* "syntax is ok" and "test is successful".
- `sudo nginx -T 2>/dev/null | grep -n -E 'broker_sign_in|ddp-broker-sign-in|include /etc/nginx/conf.d'`. *Expect:* a line `include /etc/nginx/conf.d/*.conf;` and **no** `broker_sign_in` (no name clash).
- Baseline: `curl -s -o /dev/null -w '%{http_code}\n' https://api.digitaldemocracyproject.org/docs` and `curl -s -o /dev/null -w '%{http_code}\n' https://dev.digitaldemocracyproject.org/`. *Expect:* `200` and `200`.
- Before-state of the new paths, from this host, over the tunnel address (source 10.0.0.1, which the new rule allows): `curl -s -o /dev/null -w '%{http_code}\n' --resolve dev.digitaldemocracyproject.org:443:10.0.0.1 https://dev.digitaldemocracyproject.org/_allauth/browser/v1/config`. *Expect:* `404` (the website's page, because nothing forwards this path yet).

**Step 2: get the script and read it before running it.** It is on this branch next to this note, 100 lines: `git show origin/notes/ops-handoff:notes/dev-sign-in-install-BROKER-284.sh > /tmp/dev-sign-in-install-BROKER-284.sh`, then read it. (It makes a backup `...dev.digitaldemocracyproject.org.before-284` first, writes the two files above, adds the one include line, runs `nginx -t`, and only then reloads; if `nginx -t` fails it puts everything back and stops.)

**Step 3: install.** `sudo bash /tmp/dev-sign-in-install-BROKER-284.sh install`. *Expect* the last line: "Installed and nginx reloaded." If it prints "STOPPED: ...", it changed nothing (or put everything back); report the line.

**Step 4: check, from this host.** Wait 2 seconds after the reload, then:
- Allowed address (tunnel address, source 10.0.0.1): `curl -s --resolve dev.digitaldemocracyproject.org:443:10.0.0.1 https://dev.digitaldemocracyproject.org/_allauth/browser/v1/config | head -c 300`. *Expect:* JSON containing `"google"`. And `curl -s -o /dev/null -w '%{http_code}\n' --resolve dev.digitaldemocracyproject.org:443:10.0.0.1 'https://dev.digitaldemocracyproject.org/accounts/google/login/callback/?error=access_denied'`. *Expect:* `302`.
- Refused address (loopback, which is outside `10.0.0.0/24`): `curl -s -o /dev/null -w '%{http_code}\n' --resolve dev.digitaldemocracyproject.org:443:127.0.0.1 https://dev.digitaldemocracyproject.org/_allauth/browser/v1/config` and the same for `/accounts/google/login/callback/`. *Expect:* `403` for **both** (each rule is separate; check both).
- Nothing else moved: repeat the two baseline `200` checks from step 1. *Expect:* `200` and `200`. Also glance at `sudo tail -n 20 /var/log/nginx/error.log` for anything new.

## Please report
- The step-1 outputs (including the pasted `grep` of the dev site file, minus the secret line).
- The step-3 result and the step-4 outputs, each next to what was expected.
- Anything unexpected in the nginx error log in the first few minutes.

**What this does not cover:** the real Google click-through. Ramon does that himself from the iMac on the VPN once you report green. **Please do not try to sign in.**

## Rollback
`sudo bash /tmp/dev-sign-in-install-BROKER-284.sh undo` removes the include line, the snippet and the zone file, tests nginx, and reloads. The website, `/admin` and `api.*` are not touched either way. The backup file stays in place. Undo is tested (byte-for-byte identical site file afterwards).

## Notes for context (nothing to do)
- These two paths are VPN-only on purpose; when the public sign-in screens exist (NEXT-52), the `allow`/`deny` lines come out or the website routes them itself. Production routing after the switchover is a separate decision (BROKER-203); this is a dev stopgap.
- A staff member only presents a `10.0.0.x` address if their WireGuard routes this host through the tunnel (same caveat as the existing `/admin` rule). If the iMac check later shows 403, that is the likely reason, not the rules.
