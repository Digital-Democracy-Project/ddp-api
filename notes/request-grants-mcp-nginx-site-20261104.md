# Request: one new nginx site file for `mcp.digitaldemocracyproject.org` on the civic host (AGENTS-210, epic AGENTS-203)

For the prod agent of the civic host. Posted by Agent Smith on Ramon's instruction (2026-11-03, /ask-me): the prod agent does the civic-host part; Ramon does the Mac Studio part and the database login. Plan: `ddp-infra/PLAN-grantbot-mcp.md` (decisions PR #406). Runbook: `docs/reference/grants-mcp-host.md` in ddp-agents (`main`).

## What this is
A read-only ChatGPT connector for the grants manager runs on the Mac Studio (WireGuard peer `10.0.0.8`, port 8083). This host only needs to forward one new public name to it. **Ramon's limits:** ONE new nginx site file and ONE reload. Do **not** edit any other file and do **not** touch ddp-sync or votebot. The service is **not running yet**, so after your reload the new name will answer 502; that is expected and harmless to the other sites.

## Step 0: read-only checks first, then report and wait for Ramon's "go" (a checkpoint note)
Change nothing until these are reported:
1. How the live sites are written here (certificate directives, includes, log format), and `grep -rn "mcp.digitaldemocracyproject.org" /etc/nginx` to confirm no other file uses the name.
2. **Certificate: Ramon chose DNS proof (DNS-01), with NO extra reload.** Can this host obtain a certificate for the new name by DNS-01 with the tooling the other sites use? Report yes/no and which tool. **If it cannot, stop and say so**: HTTP-01 needs a port-80 server first, which is an extra reload, and needs Ramon's fresh yes.
3. DNS: who creates the record for the new name pointing at this host, and can you? If it needs access you do not have, say so (do not guess; Ramon decides who).
4. This host's own WireGuard address (`wg show`) and that this host can reach `10.0.0.8` (the Mac Studio). Read-only; report the address, not keys.

## Step 1 (after Ramon's go): the one file and one reload
Put the file below in the sites directory **as one new file**, complete the two certificate lines the way the other sites do, then `nginx -t` (stop if it fails; do not reload), then reload **once**, then confirm the VoteBot site and `api.digitaldemocracyproject.org` still answer. Report the `nginx -t` output and the two checks.

```
server {
    listen 443 ssl;
    listen [::]:443 ssl;                                  # IPv6 too, so an AAAA record cannot land on another server
    server_name mcp.digitaldemocracyproject.org;

    # ssl_certificate / ssl_certificate_key: the same lines the other sites on this host use, for this name.

    location / {                                         # proxies every path; the service refuses anything but its own routes
        proxy_pass http://10.0.0.8:8083;           # the Mac Studio (WireGuard peer); must equal the connector's host:port
        proxy_http_version 1.1;
        proxy_buffering off;                       # streamed answers must not be held back
        proxy_read_timeout 300s;
        proxy_set_header Host $host;               # the service accepts only its own public host name (and :443)
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Connection "";
    }
}
```

## Rollback (Ramon allowed one more tested reload for this)
Delete the one file, `nginx -t`, reload, confirm the same two sites. Remove the DNS record and the certificate afterwards: until then the name points here with nothing behind it.

## Not part of this request
The Mac Studio firewall rule, the connector's background service, the read-only database login, the Google sign-in client and the ChatGPT setting (Ramon and others), and the streaming check (it needs the running service; it comes with the no-data test, AGENTS-204).
