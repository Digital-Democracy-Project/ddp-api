# DDP-API

Middleware proxy API for the Digital Democracy Project. This Flask application routes API requests through the DDP EC2 instance, which has a whitelisted IP address with Voatz.

## Purpose

This middleware handles:
- **Voatz API Authentication** - Proxy authentication to obtain WS and CSRF tokens
- **User Synchronization** - Compare and sync users between Voatz and Brevo CRM
- **Event Management** - List and create events via Voatz API
- **Brevo Segment Updates** - Bulk update contact attributes in Brevo segments

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/get_tokens` | POST | Authenticate with Voatz and receive WS/CSRF tokens |
| `/get_users` | POST | Retrieve users from Voatz (supports `?mode=diff_only`) |
| `/user_updates` | POST | Compare Voatz users with Brevo contacts and return differences |
| `/get_events` | POST | List events for an organization |
| `/create_event` | POST | Create a new event |
| `/update_segment_attribute` | POST | Bulk update an attribute for all contacts in a Brevo segment |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `API_BEARER_TOKEN` | Bearer token for authenticating requests to this middleware |
| `BREVO_RATE_LIMIT_RPH` | Brevo API rate limit (requests per hour, default: 36000) |

## Running

```bash
pip install flask requests
python middleware.py
```

The server runs on `http://0.0.0.0:5000`.

## Related Repositories

- [VoteBot](https://github.com/VotingRightsBrigade/votebot) - RAG-powered chatbot for civic engagement
