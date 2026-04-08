# DDP-API

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An open-source auth gateway and API proxy for the Digital Democracy Project. This FastAPI application routes requests to internal services (VoteBot, DDP-Sync) and external APIs (Voatz, Brevo, Webflow CMS). DDP-API has no scheduler and no background jobs — it is a stateless proxy (87-line `main.py`).

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
- **Voatz API Authentication** - Proxy authentication to obtain WS and CSRF tokens
- **Event Management** - List and create events via Voatz API
- **Brevo Segment Updates** - Bulk update contact attributes in Brevo segments
- **Webflow CMS Management** - Fill, sync, check, and manage Webflow CMS items via the [`webflow_cms`](https://github.com/VotingRightsBrigade/FillWebflowFields) package

> **Note:** Scheduled sync jobs (Voatz→Brevo, Webflow CMS batch, bill/legislator/org sync) have moved to [DDP-Sync](https://github.com/Digital-Democracy-Project/ddp-sync).

## Project Structure

```
DDP-API/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point (87 lines)
│   ├── middleware/
│   │   └── auth.py          # Bearer token authentication
│   ├── routes/
│   │   ├── voatz.py         # Voatz API endpoints
│   │   ├── brevo.py         # Brevo API endpoints
│   │   ├── ddp_sync_proxy.py # Catch-all proxy for DDP-Sync (:8001)
│   │   ├── votebot.py       # VoteBot chat proxy endpoints
│   │   └── webflow.py       # Webflow CMS management endpoints
│   └── schemas/
│       ├── common.py        # Pydantic request/response models
│       └── webflow.py       # Webflow request/response models
├── config.py                # Configuration loader (AWS/local)
├── middleware.py            # Legacy Flask app (deprecated, not imported)
├── requirements.txt
├── .env.example
└── config.local.example.json
```

## Endpoints

### Voatz/Brevo Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/get_tokens` | POST | Bearer | Authenticate with Voatz and receive WS/CSRF tokens |
| `/get_users` | POST | — | Retrieve users from Voatz (supports `?mode=diff_only`) |
| `/user_updates` | POST | — | Compare Voatz users with Brevo contacts |
| `/get_events` | POST | — | List events for an organization |
| `/create_event` | POST | — | Create a new event |
| `/update_segment_attribute` | POST | Bearer | Bulk update attributes in a Brevo segment |

### VoteBot Chat Proxy Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/votebot/chat` | POST | Bearer | Proxy chat requests to VoteBot |
| `/votebot/chat/stream` | POST | Bearer | Proxy streaming chat requests (SSE) |
| `/votebot/feedback` | POST | Bearer | Proxy feedback submissions |
| `/votebot/ws` | WebSocket | — | Bidirectional WebSocket proxy to VoteBot |

### DDP-Sync Proxy Endpoints (catch-all)

These routes forward to DDP-Sync (:8001) automatically. New DDP-Sync endpoints are available without DDP-API code changes.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/votebot/sync/{path}` | GET/POST | Bearer | Forward to DDP-Sync `/ddp-sync/v1/sync/{path}` |
| `/votebot/trigger/{path}` | GET/POST | Bearer | Forward to DDP-Sync `/ddp-sync/v1/trigger/{path}` |
| `/sync/{path}` | GET/POST | Bearer | Forward to DDP-Sync (root-level alias) |
| `/trigger/{path}` | GET/POST | Bearer | Forward to DDP-Sync (root-level alias) |

Common paths: `/votebot/sync/unified` (trigger sync), `/votebot/sync/unified/status/{id}` (poll status), `/votebot/trigger/user-sync` (Voatz→Brevo sync).

### Webflow CMS Endpoints

All Webflow endpoints require Bearer token authentication.

#### Fill endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/webflow/fill/gov-url` | POST | Bearer | Set gov-url on a single CMS item |
| `/webflow/fill/session-code` | POST | Bearer | Fill session-code, bill-prefix, and bill-number from open-states URL |
| `/webflow/fill/map-url` | POST | Bearer | Fill map-url and set bill visibility |

#### Sync endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/webflow/sync/bill-org` | POST | Bearer | Sync bill-org references (populate orgs' bills-support/bills-oppose) |
| `/webflow/sync/org-about-fields` | POST | Bearer | Parse about-organization text into structured sub-fields |

#### Check endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/webflow/check/org-missing-fields` | POST | Bearer | Check organizations for missing fields, optionally send Zapier hooks |
| `/webflow/check/duplicates` | POST | Bearer | Find duplicate and companion bills |

#### Resolve / Delete endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/webflow/resolve/duplicate-group` | POST | Bearer | Migrate content from anomalous duplicates to the correct item, then delete |
| `/webflow/items/{item_id}` | DELETE | Bearer | Delete a CMS item, optionally removing references from other collections first |

### Health Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info and version |
| `/health` | GET | Health check |
| `/docs` | GET | OpenAPI documentation (Swagger UI) |
| `/redoc` | GET | OpenAPI documentation (ReDoc) |

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_BEARER_TOKEN` | Bearer token for authenticating requests | (required) |
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
  "webflow_orgs_collection_id": "your-orgs-collection-id"
}
```

**Note:** `brevo_api_key` and `blacklist` are shared at the root level across all organizations. Each org only needs its own `brevo_list_id`. Per-org values override root-level if specified. Webflow keys can also be set via environment variables instead of the config file.

### Option 2: Local Config File (Development)

Copy `config.local.example.json` to `config.local.json` and fill in credentials.

## Running

### Install Dependencies

```bash
pip install -r requirements.txt

# Install the webflow_cms package (required for Webflow CMS endpoints)
pip install -e /path/to/FillWebflowFields
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
# Ensure EC2 instance has IAM role with Secrets Manager access
uvicorn app.main:app --host 0.0.0.0 --port 5000
```

The server runs on `http://0.0.0.0:5000`.

### Systemd Service

Update your systemd service file to use uvicorn:

```ini
[Unit]
Description=DDP-API Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/DDP-API
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000
Restart=always

[Install]
WantedBy=multi-user.target
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest tests/ -v

# Run only VoteBot proxy tests
pytest tests/test_votebot.py -v

# Run only Webflow tests
pytest tests/test_webflow.py -v
```

## API Documentation

Once running, interactive API documentation is available at:
- Swagger UI: `http://localhost:5000/docs`
- ReDoc: `http://localhost:5000/redoc`

## AWS Secrets Manager Setup

### 1. Create the Secret

```bash
aws secretsmanager create-secret \
  --name ddp-api/org-credentials \
  --description "DDP-API organization credentials" \
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
    "ddp_sync_api_key": "your-ddp-sync-api-key"
  }'
```

Or create via AWS Console:
1. Go to **AWS Secrets Manager** → **Store a new secret**
2. Select **Other type of secret**
3. Choose **Plaintext** tab and paste your JSON config
4. Name it `ddp-api/org-credentials`
5. Complete the wizard (no rotation needed)

### 2. Grant EC2 Instance Access

Create an IAM policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:ddp-api/org-credentials*"
    }
  ]
}
```

Attach this policy to your EC2 instance's IAM role.

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
```

### 3. Update Environment Variables

Add VoteBot configuration to `.env`:

```bash
echo "VOTEBOT_SERVICE_URL=http://localhost:8000" >> .env
echo "VOTEBOT_WS_URL=ws://localhost:8000/ws/chat" >> .env
echo "VOTEBOT_API_KEY=your-votebot-api-key" >> .env
```

### 4. Update Systemd Service

Edit the service file to use uvicorn instead of Flask:

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
ExecStart=/path/to/DDP-API/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ddp-api
sudo systemctl status ddp-api
```

### 5. Update Nginx Configuration

Edit your nginx config to add WebSocket support:

```bash
sudo nano /etc/nginx/sites-available/ddp-api
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Standard HTTP endpoints
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support for /votebot/ws
    location /votebot/ws {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;  # 24 hours for long-lived connections
    }
}
```

Test and reload nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 6. Verify Deployment

```bash
# Check service status
sudo systemctl status ddp-api

# View logs
sudo journalctl -u ddp-api -f

# Test endpoints
curl http://localhost:5000/health
curl https://your-domain.com/health
```

### Rollback (if needed)

If issues arise, revert to a previous commit:

```bash
cd /path/to/DDP-API
git log --oneline -5     # Find the last known-good commit
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
