# DDP-API

Middleware proxy API for the Digital Democracy Project. This Flask application routes API requests through the DDP EC2 instance, which has a whitelisted IP address with Voatz.

## Purpose

This middleware handles:
- **Voatz API Authentication** - Proxy authentication to obtain WS and CSRF tokens
- **User Synchronization** - Compare and sync users between Voatz and Brevo CRM
- **Event Management** - List and create events via Voatz API
- **Brevo Segment Updates** - Bulk update contact attributes in Brevo segments
- **Scheduled Sync** - Automatically check for user updates and push to Zapier

## Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/get_tokens` | POST | Bearer | Authenticate with Voatz and receive WS/CSRF tokens |
| `/get_users` | POST | WS/CSRF | Retrieve users from Voatz (supports `?mode=diff_only`) |
| `/user_updates` | POST | WS/CSRF | Compare Voatz users with Brevo contacts and return differences |
| `/get_events` | POST | WS/CSRF | List events for an organization |
| `/create_event` | POST | WS/CSRF | Create a new event |
| `/update_segment_attribute` | POST | Bearer | Bulk update an attribute for all contacts in a Brevo segment |
| `/trigger_sync` | POST | Bearer | Manually trigger the scheduled sync job |

## Scheduled User Sync

The app includes a background scheduler that periodically:
1. Checks all configured organizations for user changes (Voatz vs Brevo)
2. Pushes updates to a Zapier webhook only when changes are detected

This replaces polling from Zapier, reducing costs and latency.

## Configuration

### Option 1: AWS Secrets Manager (Production)

Credentials are stored in AWS Secrets Manager. The secret should contain:

```json
{
  "brevo_api_key": "xkeysib-xxx",
  "blacklist": ["voter_id_1", "voter_id_2"],
  "organizations": [
    {
      "name": "Federal",
      "voatz_email": "user@example.com",
      "voatz_password": "password",
      "voatz_org_id": 800000097,
      "brevo_list_id": 57
    },
    {
      "name": "Arizona",
      "voatz_email": "user@example.com",
      "voatz_password": "password",
      "voatz_org_id": 800000118,
      "brevo_list_id": 58
    }
  ],
  "zapier_webhook_url": "https://hooks.zapier.com/hooks/catch/xxxxx/xxxxx/",
  "sync_interval_minutes": 30
}
```

**Note:** `brevo_api_key` and `blacklist` are shared at the root level across all organizations. Each org only needs its own `brevo_list_id`. Per-org values override root-level if specified.

### Option 2: Local Config File (Development)

Copy `config.local.example.json` to `config.local.json` and fill in credentials.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_BEARER_TOKEN` | Bearer token for authenticating requests | (required) |
| `AWS_SECRET_NAME` | Secrets Manager secret name | `ddp-api/org-credentials` |
| `AWS_REGION` | AWS region | `us-east-1` |
| `LOCAL_CONFIG_PATH` | Path to local config file | `config.local.json` |
| `SYNC_INTERVAL_MINUTES` | How often to check for updates | `30` |
| `BREVO_RATE_LIMIT_RPH` | Brevo API rate limit (requests/hour) | `36000` |

## AWS Secrets Manager Setup

### 1. Create the Secret

```bash
aws secretsmanager create-secret \
  --name ddp-api/org-credentials \
  --description "DDP-API organization credentials for Voatz/Brevo sync" \
  --secret-string '{
    "brevo_api_key": "xkeysib-...",
    "blacklist": [],
    "organizations": [
      {
        "name": "Federal",
        "voatz_email": "...",
        "voatz_password": "...",
        "voatz_org_id": 800000097,
        "brevo_list_id": 57
      }
    ],
    "zapier_webhook_url": "https://hooks.zapier.com/hooks/catch/xxxxx/xxxxx/",
    "sync_interval_minutes": 30
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

## Running

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Development (Local Config)

```bash
cp config.local.example.json config.local.json
# Edit config.local.json with your credentials
python middleware.py
```

### Production (AWS Secrets Manager)

```bash
# Ensure EC2 instance has IAM role with Secrets Manager access
python middleware.py
```

The server runs on `http://0.0.0.0:5000`.

## Related Repositories

- [VoteBot](https://github.com/VotingRightsBrigade/votebot) - RAG-powered chatbot for civic engagement
