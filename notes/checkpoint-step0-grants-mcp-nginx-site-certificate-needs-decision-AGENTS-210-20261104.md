> **Reply to** `request-grants-mcp-nginx-site-20261104.md` (AGENTS-210, epic AGENTS-203). Replying on **this** branch (ddp-api `notes/ops-handoff`). **Only Step 0 (the read-only checks) was run. Nothing was changed, installed, reloaded or restarted. Step 1 (the one file and one reload) has NOT been run.** No key, secret or public IP address is in this note.

# Checkpoint (2026-11-04): Step 0 done; the certificate cannot be got by DNS proof with the tooling here, so Ramon needs to decide

Run on the civic host (`ip-172-31-81-51`). Ramon confirmed this is the civic host and asked for the Step 0 checks.

## Short answer
- **Item 2 (certificate by DNS-01): NO.** Per the request, stopping here. Step 1 waits for Ramon's decision below.
- Items 1, 3 and 4 are reported as asked. Two things to know: the DNS record already exists, and the name already answers on port 80 (see "Decisions").

## 1. How the live sites are written
- Enabled: `api.digitaldemocracyproject.org` and `dev.digitaldemocracyproject.org` (symlinks into `sites-available`), `votebot` (a real file in `sites-enabled`, HTTP only, its https redirect is commented out) and `default`.
- Certificate lines on `api` and `dev` are the standard certbot ones:
  - `ssl_certificate /etc/letsencrypt/live/<name>/fullchain.pem`
  - `ssl_certificate_key /etc/letsencrypt/live/<name>/privkey.pem`
  - `include /etc/letsencrypt/options-ssl-nginx.conf` (on `api`; `dev` does not have it)
- Logging: only the global `access_log /var/log/nginx/access.log` in `nginx.conf`. No custom log format, no per-site logs.
- `nginx.conf` includes `conf.d/*.conf` and `sites-enabled/*`. A new file is picked up from `sites-enabled`.
- `dev` already proxies to the Mac Studio at `10.0.0.8:3000`, so a `10.0.0.8` upstream has precedent here.
- `grep -rn "mcp.digitaldemocracyproject.org" /etc/nginx` (as root): **no matches**. No other file uses the name.

## 2. Certificate by DNS proof: not possible with what is installed
- certbot 1.21.0 with only the nginx plugin (`python3-certbot-nginx`). No `certbot-dns-*` plugin. No `acme.sh` or `lego`.
- Both existing certificates (`api`, `dev`) renew with `authenticator = nginx`, which is HTTP-01. The renewal hooks directories are empty.
- The zone is on Cloudflare. This host's AWS role cannot list Route 53 (not relevant, the zone is not there).
- I did not look for Cloudflare credentials on this host (a check that touched credential locations was blocked, and I did not work around it).

Ways forward, each needs Ramon:
- **A. Add DNS-01:** install `certbot-dns-cloudflare` and give it a Cloudflare API token scoped to the zone. Keeps the "no extra reload" limit, but installs a package and stores a token on this host.
- **B. Use the nginx plugin (HTTP-01):** needs a port-80 server for the name first, which is an **extra reload**. The request says this needs Ramon's fresh yes.

## 3. DNS
- **The record already exists.** `mcp.digitaldemocracyproject.org` has an A record, from the Cloudflare authoritative server, pointing at the **same address as `api.`** (this host). No AAAA, and `api.` has none either. An unrelated probe name does not resolve, so it is not a wildcard: someone created `mcp` on purpose.
- Who creates or changes records: the zone is on Cloudflare. I cannot tell who has access, or whether I do. **Ramon decides** (not guessing).
- **The name already answers on port 80.** From this host, `http://mcp.digitaldemocracyproject.org/` returns `200`, because the `default_server` site (`server_name _`) proxies to `127.0.0.1:5000`, which is DDP-API. On https the name has no certificate and fails with a name mismatch.

## 4. WireGuard
- This host's address: **`10.0.0.1/24`** on `wg0`.
- The Mac Studio peer (`10.0.0.8/32`) shows a handshake under 2 minutes old. `ping 10.0.0.8`: 2 of 2 replies, about 20 ms.
- **`10.0.0.8:8083` refuses the connection**, as expected: the service is not running yet.

## Decisions needed from Ramon before Step 1
1. **Certificate method:** A (add the DNS plugin and token) or B (HTTP-01 with an extra reload)? Or another way.
2. **Port 80 on `mcp` today:** until the new site file exists, `http://mcp...` serves DDP-API through the default server. Accept that for now, or change it as part of this work? The request's file only adds a 443 server, so by itself it does not change port 80 either.

When Ramon answers, the next step is: put the one file in place, `nginx -t` (stop if it fails), reload once, and confirm the VoteBot site and `api.` still answer.
