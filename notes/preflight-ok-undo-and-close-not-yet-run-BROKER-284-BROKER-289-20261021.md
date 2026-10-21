> **Reply to** `request-undo-sign-in-rules-and-close-public-admin-BROKER-284-BROKER-289-20261020.md` (BROKER-284, BROKER-289). Replying on **this** branch (ddp-api `notes/ops-handoff`). **Only step 1 (the read-only pre-flight) was run. Nothing was changed, reloaded or restarted. Steps 3 and 4 (the undo and the close) have NOT been run yet.** No key, secret or public IP address is in this note.

# Pre-flight (2026-10-21): every check came out as expected; waiting for the go-ahead to do steps 3 and 4

Run on the host (`ip-172-31-81-51`).

| Check | Expected | Result |
|---|---|---|
| `grep -c 'ddp-broker-sign-in.conf'` in the dev site file | `1` | `1` |
| Site file minus the include line vs `...before-284` (`cmp`) | `identical-apart-from-the-include-line` | `identical-apart-from-the-include-line` (nothing else changed since the backup) |
| `location`/`allow`/`deny` lines | the four blocks, no `allow`/`deny` | exactly the four blocks below, no `allow`/`deny` |
| `nginx -t` | syntax ok, test successful | both |
| `nginx -T` count of `BROKER-289` | `0` | `0` (not closed yet) |
| `api.../docs` | `200` | `200` |
| `dev /` | `200` | `200` |

```
16:  location = /admin {
28:  location ^~ /admin/ {
40:  location ^~ /static/ {
52:  location / {
```

## Before-state over the tunnel address (source 10.0.0.1)
| Path | Expected | Result |
|---|---|---|
| `/_allauth/browser/v1/config` | `200` | `200` |
| `/accounts/google/login/callback/?error=access_denied` | `302` | `302` |
| `/admin/login/` | report | **`200`** |
| `/static/admin/css/base.css` | report | **`200`** |

So the website's gate lets a tunnel-source request through to `/admin/login/` and `/static/...` today. After step 4 these should become `404`.

## Scripts
`close-public-admin-BROKER-289.sh` is 59 lines, as described. My copy of `dev-sign-in-install-BROKER-284.sh` in `/tmp` is byte-identical to the one on this branch. I have not run either with a changing mode.

## Not done
- Step 3 (`undo` of BROKER-284) and step 4 (`close` for BROKER-289): **not run**. They change the live nginx and need an explicit go-ahead; I will report them in a separate note when done.
- No change of any kind was made in this session.

## For Ramon
One thing to expect in step 3: after the undo, `/_allauth/...` and `/accounts/...` over loopback fall through to the `/` block and get whatever the website's gate answers for a non-VPN address. Your request expects `404`; if it shows `403` (or something else), that is the website, not the undo script, and I will report it as seen.
