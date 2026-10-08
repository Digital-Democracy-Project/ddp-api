# Answer: which ddp-sync / api-v3 / broker does ddp-api forward to? (ops session, 2026-10-08)

From the ddp-api session (Claude Code, on the ddp-api host), answering `notes/request-read-only-which-services-ddp-api-forwards-to-20261008.md`. Read-only throughout: nothing restarted, changed or deployed. No key is quoted below.

## Short answer

**ddp-api forwards `/sync/*` and `/trigger/*` to a ddp-sync running on this same host (`localhost:8001`), not to the broker EC2's ddp-sync.** That local instance serves **13 paths**, none of them `legbot-analyze-bill`, and runs a **feature branch**, not `faa9630`. That matches your count of 11 ddp-sync routes on `/docs`: the live docs merge the local instance's own `/openapi.json`, and 11 of its 13 paths are under `/sync` or `/trigger` (the other two, `/health` and `/schedule`, are not proxied). It is the missing fact for API-6.

## 1. Where the three URLs point

| Variable | Effective value (host:port) | Where it comes from |
|---|---|---|
| `DDP_SYNC_SERVICE_URL` | `localhost:8001` | **Not an environment variable at all.** `app/routes/ddp_sync_proxy.py:30` hard-codes `DDP_SYNC_SERVICE_URL = "http://localhost:8001"`. Setting the variable has no effect. (The README's env-var table lists it as configurable; it is not.) |
| `OPENSTATES_SERVICE_URL` | `10.0.0.11:8002` | `/home/ubuntu/DDP-API/.env` line 39. Not the code default (`10.0.0.8:8002`) and not what the README's table implies. |
| `EC2_BROKER_SERVICE_URL` | `10.0.0.11:8080` | `/home/ubuntu/DDP-API/.env` line 17. The code default is `localhost:8080`; the README says `10.0.0.11:8080`. |

- The systemd unit (`ddp-api.service`) sets none of the three. The running process's initial environment has none of them either; the `.env` values reach it through `load_dotenv()` in `app/main.py`, so a `/proc/<pid>/environ` check alone would wrongly show "unset".
- Both `10.0.0.11` values point at the broker EC2 host. So **api-v3 (`:8002`) and the broker (`:8080`) are on 10.0.0.11, but ddp-sync is not**: ddp-api talks to 10.0.0.11 for two of the three services and to localhost for ddp-sync.
- The ddp-api checkout here is at `da82158` (the merge of PR #24).

## 2. What answers on the ddp-sync URL

- `curl http://localhost:8001/openapi.json` gives **`13 paths; False has legbot-analyze-bill`** (title `DDP-Sync`, version `0.1.0`).
- `ss -ltnp 'sport = :8001'` shows **one `uvicorn` process** listening on `0.0.0.0:8001`. It is the systemd unit **`ddp-sync.service`** (enabled): `/home/ubuntu/ddp-sync/.venv/bin/uvicorn ddp_sync.app:app --host 0.0.0.0 --port 8001 --workers 1`, working directory `/home/ubuntu/ddp-sync`, started **2026-09-27 18:48 UTC**. No Docker on this host.
- Note it binds `0.0.0.0`, not `127.0.0.1`. I did not check what the host firewall or security group allows in, so I cannot say whether it is reachable from outside.

## 3. Is it the instance you would expect?

No, if you expected `faa9630`.

- The checkout at `/home/ubuntu/ddp-sync` is on **branch `feat/rds-openstates-routing-standalone` at commit `94c8231`** (read from the branch ref; `git` itself was not run there, so I could not check ancestry against `faa9630` or look for uncommitted edits).
- The branch's reflog shows cherry-picks of a federal-legislator routing fix and SYNC-77 (an `ocd-person/` ID-prefix fix), with the last commit on 2026-09-27 17:55 UTC. The process started about an hour **after** that, so the running code should be that checkout's HEAD, but I did not verify this against the process's loaded modules.
- It is **not** the Mac Studio (10.0.0.8) and not a different machine: it is a separate, older ddp-sync that lives on the ddp-api host itself. It is a different instance from the one on 10.0.0.11 that your prod agent reports (24 paths, includes `legbot-analyze-bill`).

## What this means for API-6 (Ramon's call, nothing changed)

- Today `/trigger/legbot-analyze-bill` cannot work through ddp-api because it forwards to a ddp-sync that lacks that route. Any fix would have to either (a) point ddp-api's ddp-sync URL at the broker host's instance or (b) deploy a newer ddp-sync here.
- Because the URL is hard-coded rather than read from the environment, (a) needs a ddp-api code change, not just a config edit.
- Two ddp-sync instances now exist (this host's `94c8231` branch and the broker host's `faa9630`). Whether both should keep running, and which one owns scheduled jobs, is outside what I checked.

## Separate from the question

One unrelated configuration finding is being reported to Ramon directly, not in this note, because this repository is public.

Nothing here blocks anything.
