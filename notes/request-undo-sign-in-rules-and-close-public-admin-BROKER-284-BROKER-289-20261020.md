> **Where this comes from.** BROKER-289 (https://digitaldemocracyproject.atlassian.net/browse/BROKER-289) and BROKER-284, ddp-broker-py. Written by the dev agent on Ramon's instruction; Ramon decided both changes after the explanation in the second section. The dev machine has no SSH to this host, on purpose, so **you run everything below on the host**. Reply on **either** this branch or ddp-broker-py's `notes/ops-handoff`, and say which. No key, secret, credential or **public IP address** goes in your reply (this repository is public).

# Request (2026-10-20, evening): (1) undo the BROKER-284 sign-in rules, (2) close `/admin` and `/static` on the public dev address, then check and report

## Why
Staff now sign in to the broker's admin at `https://admin-dev.digitaldemocracyproject.org` (BROKER-285): a name that points at the Mac Studio's VPN address and is served by the dev broker's own nginx, with its own certificate. It does not pass through this host or the website. The admin's username/password form is off there (BROKER-286), and a real Workspace Google sign-in was done on it today. So two things on **this** host's `dev.digitaldemocracyproject.org` site are no longer needed:

1. **The two BROKER-284 rules** (`/_allauth/` and `/accounts/`, VPN-only, installed earlier today from your note). Your read-only answer showed that VPN users reach this host from public addresses, so those rules refuse real staff, and staff have the new address now. Nothing on the website calls those paths (searched). The public sign-in screens (NEXT-52) will need different rules, designed later.
2. **`/admin/` and `/static/`** pass straight through to the website with **no address restriction** on this host (your answer, a0def1c: no `allow`/`deny` lines at all). The website's own gate refuses non-VPN addresses today, but this host should not depend on it. Staff no longer need those paths on this address.

## What changes, and what does not
**Change 1 (undo BROKER-284):** the script from the earlier request, `notes/dev-sign-in-install-BROKER-284.sh`, with `undo`: removes the one `include .../ddp-broker-sign-in.conf;` line from the dev site file and deletes `/etc/nginx/snippets/ddp-broker-sign-in.conf` and `/etc/nginx/conf.d/ddp-broker-sign-in-zone.conf`. The site file goes back to what it was before the install (the backup `...before-284` stays in place).
**Change 2 (close public admin):** a new script on this branch, `notes/close-public-admin-BROKER-289.sh`, with `close`: adds one line `return 404; # BROKER-289: closed, staff use admin-dev` as the first line inside each of the three blocks `location = /admin {`, `location ^~ /admin/ {` and `location ^~ /static/ {` of `/etc/nginx/sites-available/dev.digitaldemocracyproject.org`. It makes a backup first (`...before-289`), refuses unless each of the three blocks is found exactly once, runs `nginx -t`, and only then reloads. `reopen` removes exactly those lines.
**Not changed:** the `/` block, the edge secret, certificates, the `api.*` and `votebot` sites, ddp-api, ddp-sync, anything on the broker host (10.0.0.11), the website, or the broker on the Mac Studio. A **reload** only, never a restart. The same nginx serves `api.digitaldemocracyproject.org`, so nothing is reloaded unless `nginx -t` passes first.

**Known consequence (not a fault):** the website's "Staff tools" page links to `/admin` on this address; those links answer 404 once change 2 is made, until the website team points them at the new address (NEXT-66, filed). Staff use `https://admin-dev.digitaldemocracyproject.org` meanwhile.

## What I tested, and what I could not
**Tested** on a throwaway Debian nginx with a copy of the saved site file (with its `allow`/`deny` lines removed to match what you reported), 24 checks, three full runs in a row: before any change `/admin`, `/admin/`, `/admin/login/`, `/static/...` and `/` all reach the website; install then **undo of BROKER-284 gives back the original file byte for byte**; `close` (after the undo, in this order) makes the four admin and static paths answer 404, leaves `/` reaching the website, and adds exactly 3 lines and removes none; a second `close` changes nothing; `reopen` gives the original file byte for byte and the paths reach the website again; `close` stops without touching anything if a block is missing, if a block appears twice, or if nginx is already failing. **Testing found and fixed a bug in my first draft of `reopen`** (its delete command broke on a `#` in the marker text); the version on this branch is the fixed one.
**Could not test:** your real site file (I only have the saved copy and your report of its blocks), the real certificates, and the website behind it.

## Steps (you run everything on the host)

**Step 1: read-only pre-flight. Change nothing. If anything differs from "expect", STOP and report.**
- `sudo grep -c 'ddp-broker-sign-in.conf' /etc/nginx/sites-available/dev.digitaldemocracyproject.org`. *Expect:* `1` (the include line from today's install).
- `sudo cmp <(sudo grep -v 'ddp-broker-sign-in.conf' /etc/nginx/sites-available/dev.digitaldemocracyproject.org) /etc/nginx/sites-available/dev.digitaldemocracyproject.org.before-284 && echo identical-apart-from-the-include-line`. *Expect:* `identical-apart-from-the-include-line` (nothing else in the file changed since the backup; if something did, say what: it does not stop the undo, but I want to know).
- `sudo grep -n -E '^\s*(location|allow|deny)' /etc/nginx/sites-available/dev.digitaldemocracyproject.org`. *Expect:* `location = /admin {`, `location ^~ /admin/ {`, `location ^~ /static/ {` and `location / {`, **no** `allow`/`deny`. Paste the output (no secrets in it).
- `sudo nginx -t` ("syntax is ok", "test is successful") and `sudo nginx -T 2>/dev/null | grep -c 'BROKER-289'`. *Expect:* `0` (not closed yet).
- Baseline, status codes only, from this host: `curl -s -o /dev/null -w '%{http_code}\n' https://api.digitaldemocracyproject.org/docs` and `... https://dev.digitaldemocracyproject.org/`. *Expect:* `200` and `200`.
- Before-state of what will change, over the tunnel address (source 10.0.0.1): for each of `/_allauth/browser/v1/config`, `/accounts/google/login/callback/?error=access_denied`, `/admin/login/`, `/static/admin/css/base.css`: `curl -s -o /dev/null -w '%{http_code}\n' --resolve dev.digitaldemocracyproject.org:443:10.0.0.1 "https://dev.digitaldemocracyproject.org<path>"`. *Expect:* `200`, `302`, and then **report** the last two (I do not know what the website's gate answers there).

**Step 2: get the scripts and read them.** `git show origin/notes/ops-handoff:notes/dev-sign-in-install-BROKER-284.sh > /tmp/dev-sign-in-install-BROKER-284.sh` (or reuse your earlier copy if `cmp` shows it is identical) and `git show origin/notes/ops-handoff:notes/close-public-admin-BROKER-289.sh > /tmp/close-public-admin-BROKER-289.sh`. Read both (100 and 59 lines).

**Step 3: change 1.** `sudo bash /tmp/dev-sign-in-install-BROKER-284.sh undo`. *Expect:* "Removed. The sign-in rules are gone and nginx was reloaded."
**Check (2 s after):** the three over-the-tunnel requests for `/_allauth/browser/v1/config`, `/accounts/google/login/callback/?error=access_denied` now answer `404` (the website's page; before `200` and `302`); the same two with `--resolve dev.digitaldemocracyproject.org:443:127.0.0.1` answer `404` too (before `403`); `sudo cmp /etc/nginx/sites-available/dev.digitaldemocracyproject.org /etc/nginx/sites-available/dev.digitaldemocracyproject.org.before-284 && echo identical`; `/etc/nginx/snippets/ddp-broker-sign-in.conf` and `/etc/nginx/conf.d/ddp-broker-sign-in-zone.conf` are gone. **If any check differs, stop and report; do not do step 4.**

**Step 4: change 2.** `sudo bash /tmp/close-public-admin-BROKER-289.sh close`. *Expect:* "Backup: ..." then "Closed and nginx reloaded: ...".
**Check (2 s after):** `/admin`, `/admin/`, `/admin/login/` and `/static/admin/css/base.css` answer **`404`** both over the tunnel address (`--resolve ...:10.0.0.1`) and over loopback (`--resolve ...:127.0.0.1`); `/` and `api.digitaldemocracyproject.org/docs` still answer `200`; `sudo grep -c 'BROKER-289' /etc/nginx/sites-available/dev.digitaldemocracyproject.org` gives `3`; `sudo tail -n 20 /var/log/nginx/error.log` shows nothing new beyond your own requests.

## Please report
The step-1 outputs (including the pasted `grep`, no secrets), the step-3 and step-4 results each next to what was expected, anything unexpected in the nginx error log, and **whether anything else changed** (it should not have).

## Rollback
Change 2: `sudo bash /tmp/close-public-admin-BROKER-289.sh reopen` (tested byte for byte). Change 1: `sudo bash /tmp/dev-sign-in-install-BROKER-284.sh install` puts the BROKER-284 rules back (it is on this branch). Both leave the website, `api.*` and the admin on `admin-dev` as they are. Please do not run either rollback unless Ramon asks.

## Context (nothing to do)
Ramon will confirm from his side that `https://admin-dev.digitaldemocracyproject.org/admin/login/` still works after this (nothing here touches it) and will tell the website team about NEXT-66. If the iMac or any staff machine later shows a 404 at `dev.digitaldemocracyproject.org/admin/...`, that is the intended result.
