# DDP-API

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An open-source auth gateway and API proxy for the Digital Democracy Project. This FastAPI application routes requests to internal services (VoteBot, DDP-Sync) and external APIs (Voatz, Brevo, Webflow CMS). DDP-API has no scheduler and no background jobs — it is a stateless proxy.

## Architecture

```
nginx (:80/443)
  └── DDP-API (:5000) — Auth gateway + API proxy
        ├── VoteBot (:8000) — Chat/RAG
        └── DDP-Sync (:8001) — Data pipelines
```

## Purpose

This proxy handles:
- **VoteBot Chat Proxy** - Proxy chat requests to the VoteBot RAG service (HTTP, SSE streaming, WebSocket)
- **DDP-Sync Proxy** - Catch-all proxy forwarding `/sync/*` and `/trigger/*` to DDP-Sync (new endpoints in DDP-Sync are automatically available — no DDP-API code changes needed)
- **Voatz API** - Proxy authentication and pre-authenticated wrappers for read-only consumers
- **Event Management** - List and create events via Voatz API
- **Brevo Segment Updates** - Bulk update contact attributes in Brevo segments
- **Webflow CMS Management** - Fill, sync, check, and manage Webflow CMS items via the [`webflow_cms`](https://github.com/VotingRightsBrigade/FillWebflowFields) package

> **Note:** Scheduled sync jobs (Voatz→Brevo, Webflow CMS batch, bill/legislator/org sync) have moved to [DDP-Sync](https://github.com/Digital-Democracy-Project/ddp-sync).

## Project Structure

```
DDP-API/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── middleware/
│   │   └── auth.py          # read_auth / write_auth / admin_auth dependencies
│   ├── routes/
│   │   ├── voatz.py         # Voatz API endpoints + pre-authenticated wrappers
│   │   ├── brevo.py         # Brevo API endpoints
│   │   ├── admin.py         # API key management endpoints
│   │   ├── ddp_sync_proxy.py # Catch-all proxy for DDP-Sync (:8001)
│   │   ├── votebot.py       # VoteBot chat proxy endpoints
│   │   └── webflow.py       # Webflow CMS management endpoints
│   ├── schemas/
│   │   ├── common.py        # Pydantic request/response models
│   │   ├── admin.py         # Admin key management models
│   │   └── webflow.py       # Webflow request/response models
│   └── services/
│       ├── voatz.py         # Voatz HTTP client (shared by routes and wrappers)
│       └── key_store.py     # In-memory API key store backed by Secrets Manager
├── config.py                # Configuration loader (AWS/local)
├── middleware.py            # Legacy Flask app (deprecated, not imported)
├── requirements.txt
├── .env.example
└── config.local.example.json
```

## Authentication

DDP-API uses a managed API key system backed by AWS Secrets Manager. Keys have one of three scopes:

| Scope | Access |
|-------|--------|
| `read` | All read/query endpoints |
| `write` | All mutating endpoints (also satisfies `read`) |
| `admin` | Key management endpoints (`/admin/*`) only |

Keys are issued via `POST /admin/keys`, stored as SHA-256 hashes, and shown in plaintext exactly once at issuance.

### Backward-compatible env-var tokens

During initial deployment and for bootstrapping, two environment variable tokens are supported as a fallback:

| Variable | Implicit scopes |
|----------|-----------------|
| `API_BEARER_TOKEN` | `read`, `write`, `admin` |
| `API_READ_ONLY_TOKEN` | `read` |

These should be retired once managed keys are issued to all callers. See [Key Management](#key-management) below.

### Key format

Issued keys are prefixed for at-a-glance identification:
- `ddp-ro-...` — read scope
- `ddp-rw-...` — read + write scope
- `ddp-admin-...` — admin scope

### Revocation

`DELETE /admin/keys/{key_id}` takes effect immediately in the running process. Other instances pick up the change within 60 seconds (TTL cache). For immediate propagation across all instances, call `POST /admin/reload` after revoking.

## Endpoints

### Key Management (Admin)

Admin endpoints are only visible at `/admin/docs` (requires an admin-scoped key) and are excluded from the public `/docs`.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/admin/keys` | POST | **Admin** | Issue a new API key — plaintext shown once |
| `/admin/keys` | GET | **Admin** | List all keys (no hashes or plaintext) |
| `/admin/keys/{key_id}` | DELETE | **Admin** | Revoke a key immediately |
| `/admin/keys/{key_id}/rotate` | POST | **Admin** | Issue a replacement; old key expires after grace window |
| `/admin/reload` | POST | **Admin** | Force config + key store reload from Secrets Manager |

### Voatz/Brevo Endpoints

#### Passthrough — callers supply Voatz credentials or tokens

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/get_tokens` | POST | Read | Authenticate with Voatz and receive WS/CSRF tokens |
| `/get_users` | POST | Read | Retrieve users from Voatz (supports `?mode=diff_only`) |
| `/user_updates` | POST | Read | Compare Voatz users with Brevo contacts |
| `/get_events` | POST | Read | List events for an organization |
| `/create_event` | POST | **Write** | Create a new event |
| `/update_segment_attribute` | POST | **Write** | Bulk update attributes in a Brevo segment |

#### Pre-authenticated wrappers — no Voatz credentials needed

Callers need only a DDP-API read key and an `org_id`. The server fetches Voatz tokens from its own config. Useful for dev environments that should not hold Voatz credentials. If a key has an `org_ids` restriction, requests for other orgs return 403.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/voatz/users/{org_id}` | GET | Read | Fetch all users for an org |
| `/voatz/events/{org_id}` | GET | Read | Fetch events for an org (`?limit=&minTs=`) |

### VoteBot Chat Proxy Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/votebot/chat` | POST | Read | Proxy chat requests to VoteBot |
| `/votebot/chat/stream` | POST | Read | Proxy streaming chat requests (SSE) |
| `/votebot/feedback` | POST | **Write** | Proxy feedback submissions |
| `/votebot/ws` | WebSocket | — | Bidirectional WebSocket proxy to VoteBot |

### DDP-Sync Proxy Endpoints (catch-all)

These routes forward to DDP-Sync (:8001) automatically. New DDP-Sync endpoints are available without DDP-API code changes.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/votebot/sync/{path}` | GET | Read | Forward to DDP-Sync `/ddp-sync/v1/sync/{path}` |
| `/votebot/sync/{path}` | POST/PUT/DELETE | **Write** | Forward to DDP-Sync `/ddp-sync/v1/sync/{path}` |
| `/votebot/trigger/{path}` | GET | Read | Forward to DDP-Sync `/ddp-sync/v1/trigger/{path}` |
| `/votebot/trigger/{path}` | POST | **Write** | Forward to DDP-Sync `/ddp-sync/v1/trigger/{path}` |
| `/sync/{path}` | GET | Read | Forward to DDP-Sync (root-level alias) |
| `/sync/{path}` | POST/PUT/DELETE | **Write** | Forward to DDP-Sync (root-level alias) |
| `/trigger/{path}` | GET | Read | Forward to DDP-Sync (root-level alias) |
| `/trigger/{path}` | POST | **Write** | Forward to DDP-Sync (root-level alias) |

Common paths: `/votebot/sync/unified` (trigger sync), `/votebot/sync/unified/status/{id}` (poll status), `/votebot/trigger/user-sync` (Voatz→Brevo sync).

### OpenStates Proxy Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/openstates/{path}` | GET/POST | Read | Forward to local OpenStates api-v3 instance (Mac Studio via WireGuard) |

### Webflow CMS Endpoints

#### Fill endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/webflow/fill/gov-url` | POST | **Write** | Set gov-url on a single CMS item |
| `/webflow/fill/session-code` | POST | **Write** | Fill session-code, bill-prefix, and bill-number from open-states URL |
| `/webflow/fill/map-url` | POST | **Write** | Fill map-url and set bill visibility |

#### Sync endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/webflow/sync/bill-org` | POST | **Write** | Sync bill-org references (populate orgs' bills-support/bills-oppose) |
| `/webflow/sync/org-about-fields` | POST | **Write** | Parse about-organization text into structured sub-fields |

#### Check endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/webflow/check/org-missing-fields` | POST | Read | Check organizations for missing fields, optionally send Zapier hooks |
| `/webflow/check/duplicates` | POST | Read | Find duplicate and companion bills |

#### Resolve / Delete endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/webflow/resolve/duplicate-group` | POST | **Write** | Migrate content from anomalous duplicates to the correct item, then delete |
| `/webflow/items/{item_id}` | DELETE | **Write** | Delete a CMS item, optionally removing references from other collections first |

### Health Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info and version |
| `/health` | GET | Health check (no auth required) |
| `/docs` | GET | Public OpenAPI docs — Swagger UI (excludes admin endpoints) |
| `/redoc` | GET | Public OpenAPI docs — ReDoc |
| `/admin/docs` | GET | Admin OpenAPI docs — requires admin-scoped key |

## Key Management

### Issuing keys

```bash
BASE="https://your-api-domain.com"
ADMIN_TOKEN="your-admin-scoped-key"   # or API_BEARER_TOKEN during bootstrapping

# Read-only key, restricted to one org
curl -s -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "VoteBot dev", "scopes": ["read"], "restrictions": {"org_ids": ["800000001"]}}'

# Read+write key with no restrictions
curl -s -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "DDP-Sync pipeline", "scopes": ["read", "write"]}'
```

The response includes the plaintext key. **Store it securely — it will not be shown again.**

### Listing and revoking

```bash
# List all keys
curl -s $BASE/admin/keys -H "Authorization: Bearer $ADMIN_TOKEN"

# Revoke a key
curl -s -X DELETE $BASE/admin/keys/key_abc123 -H "Authorization: Bearer $ADMIN_TOKEN"

# Rotate a key (24h grace window on old key)
curl -s -X POST $BASE/admin/keys/key_abc123/rotate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"grace_hours": 24}'
```

### Key store behavior

- **Revocation latency:** Revocation takes effect immediately in the running process. Other instances pick up changes within 60 seconds (in-memory TTL cache). For immediate cross-instance propagation, call `POST /admin/reload`.
- **`last_used_at`:** Tracked in memory and flushed to Secrets Manager on graceful shutdown. This is a best-effort operational metric — `SIGKILL` or OOM kills will drop in-memory updates.
- **Secrets Manager size limit:** The `api_keys` array lives in the existing secret alongside org credentials. At ~400 bytes per key entry, ~100+ keys are supported before approaching the 64KB limit. If key volume grows significantly, `api_keys` can be moved to a dedicated secret.
- **Single-worker requirement:** The key store's Secrets Manager read-modify-write is atomic only within a single uvicorn worker. Do not add `--workers` or scale to multiple instances without adding an `asyncio.Lock` around `_secrets_manager_update` in `app/services/key_store.py`.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_BEARER_TOKEN` | Fallback write token (retire after issuing managed keys) | (optional) |
| `API_READ_ONLY_TOKEN` | Fallback read token (retire after issuing managed keys) | (optional) |
| `AWS_SECRET_NAME` | Secrets Manager secret name | `ddp-api/org-credentials` |
| `AWS_REGION` | AWS region | `us-east-1` |
| `LOCAL_CONFIG_PATH` | Path to local config file | `config.local.json` |
| `VOTEBOT_SERVICE_URL` | VoteBot HTTP service URL | `http://localhost:8000` |
| `VOTEBOT_WS_URL` | VoteBot WebSocket URL | `ws://localhost:8000/ws/chat` |
| `VOTEBOT_API_KEY` | API key for VoteBot authentication | (required for VoteBot) |
| `DDP_SYNC_SERVICE_URL` | DDP-Sync HTTP service URL | `http://localhost:8001` |
| `DDP_SYNC_API_KEY` | API key for DDP-Sync authentication (fallback) | (in Secrets Manager) |
| `VOATZ_API_BASE_URL` | Voatz API base URL | `https://api.voatz.com` |
| `VOATZ_API_ORIGIN` | Origin header for Voatz API requests | `https://api.voatz.com` |
| `WEBFLOW_API_TOKEN` | Webflow CMS API token | (required for Webflow) |
| `WEBFLOW_COLLECTION_ID` | Webflow bills collection ID | (required for Webflow) |
| `WEBFLOW_ORGS_COLLECTION_ID` | Webflow orgs collection ID | (required for Webflow) |

### Option 1: AWS Secrets Manager (Production)

Credentials are stored in AWS Secrets Manager. The secret should contain:

```json
{
  "brevo_api_key": "xkeysib-xxx",
  "blacklist": ["voter_id_1", "voter_id_2"],
  "organizations": [
    {
      "name": "Example Org",
      "voatz_email": "user@example.com",
      "voatz_password": "password",
      "voatz_org_id": 800000001,
      "brevo_list_id": 1
    }
  ],
  "zapier_webhook_url": "https://hooks.zapier.com/hooks/catch/xxxxx/xxxxx/",
  "votebot_service_url": "http://votebot-service:8000",
  "votebot_ws_url": "ws://votebot-service:8000/ws/chat",
  "votebot_api_key": "your-votebot-api-key",
  "webflow_api_token": "your-webflow-api-token",
  "webflow_bills_collection_id": "your-bills-collection-id",
  "webflow_orgs_collection_id": "your-orgs-collection-id",
  "api_keys": []
}
```

**Note:** `brevo_api_key` and `blacklist` are shared at the root level across all organizations. API keys are **no longer stored here** — they live in the dedicated `ddp-api/api-keys` secret (see "Key-store secret" under Grant EC2 Instance Access) and are populated via `POST /admin/keys` after deployment.

### Option 2: Local Config File (Development)

Copy `config.local.example.json` to `config.local.json` and fill in credentials. Key issuance via `POST /admin/keys` in dev mode writes back to `config.local.json`.

## Running

### Install Dependencies

```bash
pip install -r requirements.txt

# webflow_cms is not on PyPI — install separately from the source repo:
pip install -e /path/to/FillWebflowFields
# or directly from GitHub:
pip install git+https://github.com/VotingRightsBrigade/FillWebflowFields.git
```

### Development

```bash
# Copy and edit config
cp config.local.example.json config.local.json
cp .env.example .env
# Edit both files with your credentials

# Run with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

### Production

```bash
# Ensure EC2 instance has IAM role with Secrets Manager access (GetSecretValue + PutSecretValue)
uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1
```

The server runs on `http://0.0.0.0:5000`.

> **Important:** Always run with `--workers 1`. The key store's Secrets Manager read-modify-write is atomic only within a single uvicorn worker. Multiple workers introduce a silent lost-update race.

### Systemd Service

```ini
[Unit]
Description=DDP-API Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/DDP-API
Environment="PATH=/path/to/venv/bin"
# Secrets (API_BEARER_TOKEN, etc.) via an EnvironmentFile with chmod 600 — NOT inline
# Environment= lines (don't put secrets in the unit; it's readable).
EnvironmentFile=/etc/ddp-api/ddp-api.env
ExecStart=/path/to/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5000 --workers 1
Restart=always
RestartSec=3
# Logs go to journald — view with `journalctl -u ddp-api`. Do NOT use StandardOutput=file:
# (it silently desyncs across restarts and once hid a key-issuance error for months).
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> **Logs & a common gotcha.** ddp-api logs to stdout/stderr → journald: `journalctl -u ddp-api -n 50`.
> If `POST /admin/keys` returns **500** (`RuntimeError: Cannot persist key store: Secrets Manager
> unavailable…`), the EC2 instance role is missing **`secretsmanager:PutSecretValue`** — reads work
> with `GetSecretValue` alone, but **issuance/revocation/rotation need the write** (see the IAM
> policy above). Add it on `…:secret:ddp-api/org-credentials*`; no restart needed.

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run only admin/key management tests
pytest tests/test_admin.py -v

# Run only Webflow tests
pytest tests/test_webflow.py -v
```

## API Documentation

Once running, interactive API documentation is available at:
- **Public Swagger UI:** `http://localhost:5000/docs` — shows all endpoints except admin
- **Public ReDoc:** `http://localhost:5000/redoc`
- **Admin Swagger UI:** `http://localhost:5000/admin/docs` — requires an admin-scoped key; shows key management endpoints

## AWS Secrets Manager Setup

### 1. Create the Secret

```bash
aws secretsmanager create-secret \
  --name ddp-api/org-credentials \
  --description "DDP-API organization credentials and API keys" \
  --secret-string '{
    "brevo_api_key": "xkeysib-...",
    "blacklist": [],
    "organizations": [
      {
        "name": "Example Org",
        "voatz_email": "...",
        "voatz_password": "...",
        "voatz_org_id": 800000001,
        "brevo_list_id": 1
      }
    ],
    "zapier_webhook_url": "https://hooks.zapier.com/hooks/catch/xxxxx/xxxxx/",
    "ddp_sync_api_key": "your-ddp-sync-api-key",
    "api_keys": []
  }'
```

### 2. Grant EC2 Instance Access

Create an IAM policy (note: `PutSecretValue` is required for key issuance and revocation):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:PutSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:ddp-api/org-credentials*",
        "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:ddp-api/api-keys*"
      ]
    }
  ]
}
```

Attach this policy to your EC2 instance's IAM role.

**Key-store secret (`ddp-api/api-keys`).** API keys live in their own secret —
decoupled from the Voatz `org-credentials` blob (`config.API_KEYS_SECRET_NAME`,
default `ddp-api/api-keys`; see `PLAN_key_management.md` addendum 2026-06-27).
The EC2 role above only needs `GetSecretValue`+`PutSecretValue` on this secret at
runtime — it does **not** get `CreateSecret`. Create the secret **once** with an
**admin identity** (AWS Console, or an admin CLI profile — not the EC2 instance
role), seeded from any keys currently in `org-credentials`:

```bash
# Run with an admin profile that has CreateSecret + GetSecretValue on org-credentials.
KEYS=$(aws secretsmanager get-secret-value --secret-id ddp-api/org-credentials \
        --region us-east-1 --query SecretString --output text \
        | jq -c '{api_keys: (.api_keys // [])}')
aws secretsmanager create-secret --name ddp-api/api-keys --region us-east-1 \
  --secret-string "$KEYS"
```

A missing-`PutSecretValue` write at runtime now **fails loudly** (500 on issue)
instead of silently falling back to a host-local file.

### 3. Verify Access

```bash
aws secretsmanager get-secret-value --secret-id ddp-api/org-credentials
```

## Deployment (EC2)

### 1. Update Code

```bash
ssh ubuntu@your-ec2-instance
cd /path/to/DDP-API
git pull origin main
```

### 2. Install Dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt
# Note: webflow_cms is pre-installed on the server — no action needed unless updating it
```

### 3. Update Systemd Service

Ensure `--workers 1` is present in `ExecStart`:

```bash
sudo nano /etc/systemd/system/ddp-api.service
```

```ini
[Unit]
Description=DDP-API Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/DDP-API
Environment="PATH=/path/to/DDP-API/venv/bin"
ExecStart=/path/to/DDP-API/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5000 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart ddp-api
sudo systemctl status ddp-api
```

### 4. Update Nginx Configuration

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /votebot/ws {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 5. Bootstrap Managed Keys

After deploying, issue managed keys using the existing `API_BEARER_TOKEN`:

```bash
BASE="https://your-domain.com"
BOOTSTRAP="$API_BEARER_TOKEN"

# Admin key for operators
curl -s -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $BOOTSTRAP" \
  -H "Content-Type: application/json" \
  -d '{"name": "Ops admin", "scopes": ["admin"]}'

# Write key for DDP-Sync
curl -s -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $BOOTSTRAP" \
  -H "Content-Type: application/json" \
  -d '{"name": "DDP-Sync pipeline", "scopes": ["read", "write"]}'

# Read-only key for VoteBot dev (org-restricted)
curl -s -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $BOOTSTRAP" \
  -H "Content-Type: application/json" \
  -d '{"name": "VoteBot dev", "scopes": ["read"], "restrictions": {"org_ids": ["800000001"]}}'
```

Once all callers have migrated to managed keys, remove `API_BEARER_TOKEN` and `API_READ_ONLY_TOKEN` from `.env` and restart the service.

### 6. Verify Deployment

```bash
sudo systemctl status ddp-api
sudo journalctl -u ddp-api -f
curl http://localhost:5000/health
curl https://your-domain.com/health
```

### Rollback (if needed)

```bash
cd /path/to/DDP-API
git log --oneline -5
git checkout <commit>
sudo systemctl restart ddp-api
```

## Related Repositories

- [DDP-Sync](https://github.com/Digital-Democracy-Project/ddp-sync) - Unified data pipeline service (scheduled sync jobs)
- [VoteBot](https://github.com/Digital-Democracy-Project/votebot) - RAG-powered chatbot for civic engagement
- [Chat Widget](https://github.com/VotingRightsBrigade/chat-widget-poc) - Embeddable chat widget for VoteBot
- [FillWebflowFields](https://github.com/VotingRightsBrigade/FillWebflowFields) - Webflow CMS management package (`webflow_cms`)

## License

This project is open source and available under the [MIT License](LICENSE).
