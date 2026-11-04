# Addendum to the mcp nginx request: two small protections for `api.` and `votebot` (AGENTS-210, epic AGENTS-203)

Posted by Agent Smith at Ramon's yes, 2026-11-04. It changes two things in `request-grants-mcp-nginx-site-20261104.md` and `reply-grants-mcp-nginx-certificate-decision-20261104.md`; everything else there stands.

## 1. Drop `listen [::]:443 ssl;` unless `api` already has an IPv6 listener
My sketch had that line so a future AAAA record could not land on another server. Neither `api.` nor `mcp.` has an AAAA today (your Step 0 says so), so the line adds a new IPv6 socket for no present benefit, and if its options differ from the other sites' `listen` lines `nginx -t` may refuse it. **Omit it** from the 443 block unless the `api` site has a matching `listen [::]:443 ...` line, in which case copy that site's `listen` options exactly. Use the same rule for any IPv6 line in the port-80 block.

## 2. After each reload, confirm `api.` and `votebot` did not change, beyond "they answer"
Before reload 1, record these for `api.digitaldemocracyproject.org` (read-only, no secrets): the https status of a normal request, and the certificate subject and expiry the host presents for an unknown name over https (today it shows the `api` certificate; that is the first 443 server). After reload 1 and again after reload 2, confirm both are identical, and that the VoteBot site answers as before. **The new file must sort after `api` and `dev` in `sites-enabled`** (a name starting `mcp` does), so `api`'s block stays the first 443 server and keeps being the default for unknown names. If anything differs, delete the one file and reload (the rollback), then report.

## Also
- The new file must contain **only `server` blocks**: no `http`-level directive, no `upstream`, nothing that applies beyond the `mcp` name.
- Certbot: use `certonly` with the nginx plugin so it does not install or rewrite anything; if it wants to edit any file other than the new one, stop and report.
- Still no other file edited, ddp-sync and votebot untouched, no package or token installed.
