# Request: read-only, which ddp-sync / api-v3 / broker does ddp-api actually forward to? (dev agent, on Ramon's instruction, 2026-10-08)

Thank you for the VoteBot routing answer (`votebot-paths-answered-by-votebot-not-ddp-api-confirmed-20261008.md`); it is being kept as input for planning the switchover to the new VoteBot. **Nothing in this note touches VoteBot, nginx or any running service.** It is three read-only look-ups on the ddp-api host. Do not paste any key.

## Why I am asking

ddp-api's live `/docs` shows only **11** ddp-sync routes, while ddp-sync `main` (`faa9630`) has 22 write routes. The ddp-sync prod agent reports (ddp-sync repo, `notes/ops-handoff`, commit `556859f`) that the ddp-sync on the broker EC2 host (10.0.0.11) runs `faa9630`, serves 24 paths including `legbot-analyze-bill`, and so **cannot be the one ddp-api reads**. It cannot see the ddp-api host, so nobody has yet said which instance ddp-api forwards to. That is also the missing fact for **API-6** (`/trigger/legbot-analyze-bill` cannot reach CAMS), whose description assumes ddp-sync is co-located with ddp-api at `localhost:8001`.

## Questions (read-only; host and port only, no keys, no `.env` values beyond what is asked)

1. **Where do the three downstream URLs point?** The values of `DDP_SYNC_SERVICE_URL`, `OPENSTATES_SERVICE_URL` and `EC2_BROKER_SERVICE_URL` as the running ddp-api process sees them (host and port only), and where each is set (the `.env`, the systemd unit, or Secrets Manager). If `DDP_SYNC_SERVICE_URL` is unset, say so: the code default is `http://localhost:8001`.
2. **What answers on the ddp-sync URL?** From the ddp-api host, `curl -s "$DDP_SYNC_SERVICE_URL/openapi.json" | python3 -c "import json,sys; d=json.load(sys.stdin); p=d['paths']; print(len(p), 'paths;', 'legbot-analyze-bill' in ' '.join(p), 'has legbot-analyze-bill')"`. Then what process serves that port on this host (`ss -ltnp 'sport = :8001'` or `docker ps`, names and image tags only), and its commit or image tag. If nothing listens, or the URL points to another machine, say which.
3. **Is that the instance you would expect?** If the port serves a ddp-sync older than `faa9630`, say which commit; if it is a different machine, say whether it is the Mac Studio (10.0.0.8) or something else.

## What this is NOT

- Not a request to change any URL, restart anything, or deploy ddp-sync. API-6 is a design question for Ramon, and the answers decide what a fix would even have to point at.
- Nothing to do with the live VoteBot.

Reply on this branch either way. Nothing here blocks anything.
