# DDP-API Key Management Plan

> **Status:** APPROVED — ready to implement  
> **Scope:** API key issuance, scoping, storage, admin endpoints, Voatz service layer, and pre-authenticated wrapper endpoints

---

## Decisions Log

| # | Question | Decision |
|---|---|---|
| Q1 | Separate `admin` scope? | Yes. `write_auth` protects data endpoints; `admin_auth` protects `/admin/*`. Env-var `API_BEARER_TOKEN` implicitly gets `["read", "write", "admin"]` for bootstrapping. |
| Q2 | `last_used_at` flush timing | Flush-on-shutdown in the lifespan context manager. |
| Q3 | Wrapper endpoint method | GET for read wrappers (`/voatz/users/{org_id}`, `/voatz/events/{org_id}`). |
| Q4 | `diff_only` in wrapper | Existing `/get_users?mode=diff_only` endpoint is **untouched**. New GET wrappers are simple read-all only. No ddp-sync migration needed. |
| Q5 | `/docs` exposure | Two-schema approach: public `/docs` (no admin routes) + auth-gated `/admin/docs` (admin-scoped key required). |
| Q6 | Python version | 3.10.12 on EC2 — `dict \| None` is fine in production. Fix it anyway for test-runner compat (3.9). |

---

## Overview

This plan covers three connected bodies of work:

1. **Voatz service layer** — extract duplicated Voatz HTTP logic into `app/services/voatz.py`, enabling pre-authenticated GET wrapper endpoints for read-only clients (e.g. VoteBot dev) who should not hold Voatz credentials.
2. **Key management system** — replace flat env-var tokens with a structured API key store backed by AWS Secrets Manager, supporting three scopes (`read`, `write`, `admin`) and optional per-org restrictions.
3. **Admin endpoints + split docs** — `POST/GET/DELETE /admin/keys` for programmatic key issuance and revocation, with a public `/docs` and a separate auth-gated `/admin/docs`.

---

## Goals

- Read-only clients call `GET /voatz/users/{org_id}` or `GET /voatz/events/{org_id}` with only a DDP-API key — no Voatz credentials needed
- Keys have explicit scopes (`read`, `write`, `admin`) and optional org/endpoint restrictions
- Keys are issued and revoked via admin endpoints, without redeploying
- Keys are stored hashed; the plaintext is shown exactly once at issuance
- Public `/docs` never exposes admin endpoints — safe to show in a self-service portal
- The existing `API_BEARER_TOKEN` / `API_READ_ONLY_TOKEN` env vars continue to work as a fallback

---

## Affected Files

| File | Change |
|---|---|
| `app/services/__init__.py` | **New** |
| `app/services/voatz.py` | **New** — Voatz HTTP client |
| `app/services/key_store.py` | **New** — key store with TTL cache |
| `app/routes/admin.py` | **New** — admin endpoints |
| `app/schemas/admin.py` | **New** — admin request/response models |
| `app/middleware/auth.py` | **Modified** — key store lookup + `admin_auth` dependency |
| `app/routes/voatz.py` | **Modified** — use service layer; add GET wrapper endpoints |
| `app/routes/brevo.py` | **Modified** — use service layer for Voatz fetch in `/user_updates` |
| `app/main.py` | **Modified** — split docs, register admin router, flush on shutdown |
| `config.py` | **Minor** — fix `dict \| None` → `Optional[dict]` for Python 3.9 test compat |
| `config.local.example.json` | **Modified** — add `api_keys` example |
| `tests/conftest.py` | **Modified** — update fixtures for new auth system |
| `tests/test_admin.py` | **New** — admin endpoint and docs tests |
| `requirements.txt` | **No change** — all new code uses stdlib only |
| `README.md` | **Modified** — update auth, admin, and docs sections |

---

## Phase 1: Voatz Service Layer

### Problem
`brevo.py`'s `/user_updates` independently re-implements the same paginated Voatz user fetch that lives in `voatz.py`'s `/get_users` (~60 duplicate lines). Both will need to call the same functions once wrapper endpoints are added. Extracting a service layer fixes this before adding new consumers.

### New file: `app/services/voatz.py`

```python
"""Voatz HTTP client — shared by route handlers and pre-authenticated wrapper endpoints."""

import logging
import os
import requests
from fastapi import HTTPException

logger = logging.getLogger(__name__)

VOATZ_API_BASE   = os.getenv("VOATZ_API_BASE_URL", "https://api.voatz.com")
LOGIN_URL        = f"{VOATZ_API_BASE}/voatz/organizations/users/login"
USERS_URL        = f"{VOATZ_API_BASE}/voatz/customers/delegate/signups/byorg"
EVENTS_URL       = f"{VOATZ_API_BASE}/voatz/events/listbyorganization/chrono"
CREATE_EVENT_URL = f"{VOATZ_API_BASE}/voatz/events/create"

VOATZ_HEADERS = {
    "Accept-Encoding": "identity",
    "Content-Type": "application/json",
    "Origin": os.getenv("VOATZ_API_ORIGIN", VOATZ_API_BASE),
}


def fetch_tokens(email: str, password: str, org_id: int) -> dict:
    """Authenticate with Voatz. Returns {"WS": ..., "Csrf-Token": ...}."""
    payload = {
        "emailAddress": email,
        "password": password,
        "authData": [{"key": "organizationid", "value": str(org_id)}],
    }
    try:
        resp = requests.post(LOGIN_URL, headers=VOATZ_HEADERS, json=payload, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Voatz login failed: {e}")

    if resp.status_code == 200 and resp.text.strip() == "OK":
        ws   = resp.cookies.get("WS")        or resp.headers.get("WS")
        csrf = resp.cookies.get("Csrf-Token") or resp.headers.get("Csrf-Token")
        if ws and csrf:
            return {"WS": ws, "Csrf-Token": csrf}
        raise HTTPException(status_code=500, detail="Tokens not found in Voatz response")

    raise HTTPException(
        status_code=502,
        detail=f"Voatz login failed: {resp.status_code} {resp.text}",
    )


def fetch_tokens_from_config(org_id: int) -> dict:
    """
    Look up org credentials from config and call fetch_tokens().
    Used by GET wrapper endpoints — the caller never sees Voatz credentials.
    """
    from config import get_config
    config = get_config()
    org = next(
        (o for o in config.get("organizations", []) if o.get("voatz_org_id") == org_id),
        None,
    )
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")
    return fetch_tokens(org["voatz_email"], org["voatz_password"], org_id)


def fetch_users(ws_token: str, csrf_token: str, org_id: int) -> list:
    """Paginated fetch of all users for an org. Returns raw result list."""
    headers = {
        **VOATZ_HEADERS,
        "WS": ws_token,
        "Csrf-Token": csrf_token,
        "Cookie": f"WS={ws_token}; Csrf-Token={csrf_token}",
    }
    users, min_id = [], None
    while True:
        payload = {"organizationId": int(org_id), "limit": 1000}
        if min_id:
            payload["minId"] = min_id
        try:
            resp = requests.post(USERS_URL, headers=headers, json=payload, timeout=60)
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Voatz users request failed: {e}")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Voatz returned {resp.status_code}")
        data   = resp.json()
        result = data.get("result", [])
        if not result:
            break
        users.extend(result)
        min_id = data.get("minId")
    return users


def fetch_events(
    ws_token: str,
    csrf_token: str,
    org_id: int,
    limit: int = None,
    min_ts: int = None,
) -> object:
    """Fetch events for an org. Returns raw Voatz response JSON."""
    headers = {
        **VOATZ_HEADERS,
        "WS": ws_token,
        "Csrf-Token": csrf_token,
        "Cookie": f"WS={ws_token}; Csrf-Token={csrf_token}",
    }
    payload = {"organizationId": org_id}
    if limit:
        payload["limit"] = limit
    if min_ts:
        payload["minTs"] = min_ts
    try:
        resp = requests.post(EVENTS_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Voatz events request failed: {e}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Voatz returned {resp.status_code}")
    return resp.json()
```

### Changes to `routes/voatz.py`
- Remove the module-level URL constants and `VOATZ_HEADERS` (they move into the service)
- Replace inline HTTP logic in `get_tokens`, `get_users`, and `get_events` with calls to the service functions
- Existing endpoint paths, request/response shapes, and `?mode=diff_only` behavior are **unchanged**

### Changes to `routes/brevo.py`
`/user_updates` (lines 174–211) re-implements the paginated user fetch. Replace that block with:
```python
from app.services.voatz import fetch_users
users = fetch_users(ws_token, csrf_token, organization_id)
```
The rest of the `/user_updates` logic (Brevo fetch, diff calculation) is unchanged.

---

## Phase 2: Key Data Model

### Scopes

| Scope | Access |
|---|---|
| `read` | All read/query endpoints |
| `write` | All mutating endpoints (implies `read`) |
| `admin` | `/admin/*` endpoints only — key management, docs, reload |

Env-var fallback implicit scopes:
- `API_BEARER_TOKEN` → `["read", "write", "admin"]` (bootstrapping)
- `API_READ_ONLY_TOKEN` → `["read"]`

### Schema stored in Secrets Manager

The `api_keys` array is added as a top-level field alongside `organizations`:

```json
{
  "organizations": [...],
  "api_keys": [
    {
      "id": "key_a1b2c3",
      "name": "VoteBot dev",
      "key_hash": "e3b0c44298fc1c149afb...sha256...",
      "prefix": "ddp-ro",
      "scopes": ["read"],
      "restrictions": {
        "org_ids": ["800000001"],
        "endpoints": null
      },
      "created_at": "2026-06-17T00:00:00Z",
      "expires_at": null,
      "last_used_at": null
    },
    {
      "id": "key_d4e5f6",
      "name": "DDP-Sync pipeline",
      "key_hash": "abc123...sha256...",
      "prefix": "ddp-rw",
      "scopes": ["read", "write"],
      "restrictions": {},
      "created_at": "2026-06-17T00:00:00Z",
      "expires_at": null,
      "last_used_at": null
    }
  ]
}
```

### Field reference

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | `"key_" + secrets.token_hex(6)` — public reference ID, safe to log |
| `name` | `str` | Human-readable label |
| `key_hash` | `str` | `sha256(plaintext_key)` — plaintext never stored |
| `prefix` | `str` | `"ddp-ro"`, `"ddp-rw"`, or `"ddp-admin"` — encoded in key for at-a-glance ID |
| `scopes` | `list[str]` | `["read"]`, `["write"]`, `["admin"]`, or combinations |
| `restrictions.org_ids` | `list[str] \| null` | If set, key only works for these `org_id` values on org-scoped endpoints |
| `restrictions.endpoints` | `list[str] \| null` | Reserved for future endpoint-level scoping |
| `created_at` | `str` | ISO 8601 UTC |
| `expires_at` | `str \| null` | ISO 8601 UTC. `null` = never expires |
| `last_used_at` | `str \| null` | Updated in-memory; flushed to Secrets Manager on shutdown |

### Key format

Plaintext keys: `{prefix}-{secrets.token_urlsafe(32)}`

Examples:
- `ddp-ro-Xk9mN2pQ...` (read)
- `ddp-rw-aB3cD7eF...` (read + write)
- `ddp-admin-zZ1yY2xX...` (admin only)

---

## Phase 3: Key Store Service

### Known limitations (intentional)

**Revocation latency:** Revoked keys remain usable for up to 60s while the in-memory cache is still warm on the running instance. This is an intentional trade-off — Secrets Manager is not a low-latency store. For urgent revocation (compromised key), `POST /admin/reload` bypasses the TTL and invalidates immediately. This SLA should be documented in the README and communicated to API consumers.

**`last_used_at` durability:** `last_used_at` is tracked in memory and flushed to Secrets Manager on graceful shutdown only. A `SIGKILL`, OOM kill, or unclean restart will drop any in-memory updates since the last flush. This field is a best-effort operational metric for identifying stale keys — it is not a security control. Code comments will make this explicit.

**Secrets Manager 64KB limit:** The entire secret JSON (org credentials + api_keys array) must stay under 64KB. At ~400 bytes per key entry, this supports ~100+ keys alongside existing org credentials — well beyond current needs. If key volume grows significantly, the `api_keys` array can be moved to a separate dedicated secret. Document the limit in README.

### New file: `app/services/key_store.py`

```python
"""In-memory API key store backed by AWS Secrets Manager."""

import hashlib
import logging
import secrets
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60


class ApiKey:
    def __init__(self, data: dict):
        self.id           = data["id"]
        self.name         = data["name"]
        self.key_hash     = data["key_hash"]
        self.prefix       = data["prefix"]
        self.scopes       = data.get("scopes", [])
        self.restrictions = data.get("restrictions", {})
        self.created_at   = data["created_at"]
        self.expires_at   = data.get("expires_at")
        self.last_used_at = data.get("last_used_at")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "key_hash": self.key_hash,
            "prefix": self.prefix, "scopes": self.scopes,
            "restrictions": self.restrictions, "created_at": self.created_at,
            "expires_at": self.expires_at, "last_used_at": self.last_used_at,
        }


class KeyStore:
    def __init__(self):
        self._lock      = threading.Lock()
        self._by_hash   = {}   # key_hash -> ApiKey
        self._by_id     = {}   # key_id   -> ApiKey
        self._loaded_at = None

    def _load_from_config(self):
        from config import get_config
        config   = get_config()
        by_hash, by_id = {}, {}
        for entry in config.get("api_keys", []):
            key = ApiKey(entry)
            by_hash[key.key_hash] = key
            by_id[key.id]         = key
        with self._lock:
            self._by_hash   = by_hash
            self._by_id     = by_id
            self._loaded_at = datetime.now(timezone.utc)

    def _maybe_refresh(self):
        if self._loaded_at is None:
            self._load_from_config()
            return
        age = (datetime.now(timezone.utc) - self._loaded_at).total_seconds()
        if age > CACHE_TTL_SECONDS:
            self._load_from_config()

    def reload(self):
        self._load_from_config()

    def get_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        self._maybe_refresh()
        return self._by_hash.get(key_hash)

    def list_all(self) -> list:
        self._maybe_refresh()
        return list(self._by_id.values())

    def issue(
        self,
        name: str,
        scopes: list,
        restrictions: dict,
        expires_at: Optional[str] = None,
    ) -> tuple:
        """Generate a new key, persist to Secrets Manager. Returns (plaintext, ApiKey)."""
        if "admin" in scopes:
            prefix = "ddp-admin"
        elif "write" in scopes:
            prefix = "ddp-rw"
        else:
            prefix = "ddp-ro"

        plaintext = f"{prefix}-{secrets.token_urlsafe(32)}"
        key_hash  = hashlib.sha256(plaintext.encode()).hexdigest()
        key_id    = "key_" + secrets.token_hex(6)
        now       = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        entry = {
            "id": key_id, "name": name, "key_hash": key_hash,
            "prefix": prefix, "scopes": scopes, "restrictions": restrictions or {},
            "created_at": now, "expires_at": expires_at, "last_used_at": None,
        }
        key = ApiKey(entry)
        _secrets_manager_update(lambda keys: keys + [entry])
        with self._lock:
            self._by_hash[key_hash] = key
            self._by_id[key_id]     = key
        return plaintext, key

    def revoke(self, key_id: str) -> bool:
        """Remove a key by ID. Returns False if not found."""
        with self._lock:
            key = self._by_id.pop(key_id, None)
            if not key:
                return False
            self._by_hash.pop(key.key_hash, None)
        _secrets_manager_update(lambda keys: [k for k in keys if k["id"] != key_id])
        return True

    def rotate(self, key_id: str, grace_hours: int = 24) -> tuple:
        """
        Issue a replacement key with the same scopes/restrictions.
        Set expires_at on the old key for the grace window.
        Returns (new_plaintext, new_ApiKey, old_expires_at).
        """
        with self._lock:
            old_key = self._by_id.get(key_id)
        if not old_key:
            raise KeyError(key_id)

        expires = (
            datetime.now(timezone.utc) + timedelta(hours=grace_hours)
        ).isoformat().replace("+00:00", "Z")

        plaintext, new_key = self.issue(
            name=f"{old_key.name} (rotated)",
            scopes=old_key.scopes,
            restrictions=old_key.restrictions,
            expires_at=None,
        )
        old_key.expires_at = expires
        _secrets_manager_update(
            lambda keys: [
                {**k, "expires_at": expires} if k["id"] == key_id else k
                for k in keys
            ]
        )
        return plaintext, new_key, expires

    def flush_last_used(self):
        """Write in-memory last_used_at values back to Secrets Manager. Called on shutdown."""
        in_memory = {
            k.id: k.last_used_at
            for k in self._by_id.values()
            if k.last_used_at
        }
        if not in_memory:
            return

        def _update(keys):
            for k in keys:
                if k["id"] in in_memory:
                    k["last_used_at"] = in_memory[k["id"]]
            return keys

        try:
            _secrets_manager_update(_update)
            logger.info("Flushed last_used_at for %d keys", len(in_memory))
        except Exception as e:
            logger.error("Failed to flush last_used_at: %s", e)


def _secrets_manager_update(transform):
    """Read-modify-write: apply transform to api_keys list in Secrets Manager.

    Uses synchronous boto3 intentionally. Synchronous calls block the entire
    asyncio event loop thread, so no other coroutine can interleave during the
    get→modify→put sequence — making RMW effectively atomic within a single
    uvicorn worker. If this is ever refactored to use aiobotocore (async boto3),
    an asyncio.Lock must be added to prevent concurrent coroutines from
    interleaving and producing lost updates.
    """
    import boto3
    import json
    from config import AWS_SECRET_NAME, AWS_REGION
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    resp   = client.get_secret_value(SecretId=AWS_SECRET_NAME)
    secret = json.loads(resp["SecretString"])
    secret["api_keys"] = transform(secret.get("api_keys", []))
    client.put_secret_value(
        SecretId=AWS_SECRET_NAME,
        SecretString=json.dumps(secret),
    )


_key_store = None


def get_key_store() -> KeyStore:
    global _key_store
    if _key_store is None:
        _key_store = KeyStore()
    return _key_store
```

---

## Phase 4: Updated Auth Middleware

### New `app/middleware/auth.py`

```python
"""Bearer token authentication — key store lookup with env-var fallback."""

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()


class _EnvVarKey:
    """Synthetic key for env-var token backward compatibility."""
    def __init__(self, scopes: list):
        self.id           = "env-var"
        self.scopes       = scopes
        self.restrictions = {}
        self.expires_at   = None


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _check_expired(key) -> bool:
    if not key.expires_at:
        return False
    expires = datetime.fromisoformat(key.expires_at.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) > expires


async def _resolve(credentials: HTTPAuthorizationCredentials):
    """Resolve bearer token to a key object. Raises 401/403 on failure."""
    token = credentials.credentials

    # Key store lookup (primary path)
    from app.services.key_store import get_key_store
    key = get_key_store().get_by_hash(_hash(token))
    if key:
        if _check_expired(key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key expired",
            )
        # Track last_used_at in memory (flushed to Secrets Manager on shutdown)
        key.last_used_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        logger.info("auth key_id=%s name=%r", key.id, key.name)
        return key

    # Env-var fallback — API_BEARER_TOKEN gets full access including admin
    write_token = os.getenv("API_BEARER_TOKEN", "")
    read_token  = os.getenv("API_READ_ONLY_TOKEN", "")
    if write_token and token == write_token:
        return _EnvVarKey(scopes=["read", "write", "admin"])
    if read_token and token == read_token:
        return _EnvVarKey(scopes=["read"])

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid Bearer token",
    )


async def write_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Require write scope. Use on mutating data endpoints."""
    key = await _resolve(credentials)
    if "write" not in key.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required",
        )
    return key


async def read_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Require read scope. Write scope also satisfies this."""
    key = await _resolve(credentials)
    if "read" not in key.scopes and "write" not in key.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read access required",
        )
    return key


async def admin_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Require admin scope. Use on /admin/* endpoints and admin docs."""
    key = await _resolve(credentials)
    if "admin" not in key.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return key


# Backward-compatibility alias
bearer_auth = write_auth
```

### Route handler signature changes

All route handlers currently declare `token: str = Depends(write_auth)` but never use the variable. Change the unused parameter name to `_key` (no type annotation needed — FastAPI infers from the dependency):

```python
# Before
async def create_event(data: dict, token: str = Depends(write_auth)):

# After
async def create_event(data: dict, _key=Depends(write_auth)):
```

This touches ~25 route handler signatures across 6 files. It is purely cosmetic — no logic changes.

---

## Phase 5: Admin Endpoints & Schemas

### New file: `app/schemas/admin.py`

```python
from typing import Optional
from pydantic import BaseModel


class IssueKeyRequest(BaseModel):
    name: str
    scopes: list                    # ["read"] | ["write"] | ["admin"] | combinations
    restrictions: Optional[dict] = None   # {"org_ids": [...], "endpoints": [...]}
    expires_at: Optional[str] = None      # ISO 8601 UTC


class IssueKeyResponse(BaseModel):
    id: str
    key: str                        # plaintext — shown ONCE
    name: str
    scopes: list
    restrictions: Optional[dict]
    created_at: str
    expires_at: Optional[str]
    message: str


class ApiKeyInfo(BaseModel):
    id: str
    name: str
    prefix: str
    scopes: list
    restrictions: Optional[dict]
    created_at: str
    expires_at: Optional[str]
    last_used_at: Optional[str]


class ListKeysResponse(BaseModel):
    keys: list
    total: int


class RevokeKeyResponse(BaseModel):
    status: str
    id: str
    message: str


class RotateKeyRequest(BaseModel):
    grace_hours: int = 24


class RotateKeyResponse(BaseModel):
    new_key_id: str
    new_key: str                    # plaintext — shown ONCE
    old_key_id: str
    old_key_expires_at: str
    message: str
```

### New file: `app/routes/admin.py`

```python
"""Admin endpoints for API key management. Protected by admin_auth."""

import logging
from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import admin_auth
from app.schemas.admin import (
    IssueKeyRequest, IssueKeyResponse,
    ListKeysResponse, ApiKeyInfo,
    RevokeKeyResponse,
    RotateKeyRequest, RotateKeyResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)


@router.post("/keys", response_model=IssueKeyResponse)
async def issue_key(req: IssueKeyRequest, _key=Depends(admin_auth)):
    """Issue a new API key. The plaintext is shown exactly once — store it securely."""
    from app.services.key_store import get_key_store
    plaintext, key = get_key_store().issue(
        name=req.name,
        scopes=req.scopes,
        restrictions=req.restrictions or {},
        expires_at=req.expires_at,
    )
    return IssueKeyResponse(
        id=key.id, key=plaintext, name=key.name, scopes=key.scopes,
        restrictions=key.restrictions, created_at=key.created_at,
        expires_at=key.expires_at,
        message="Store this key securely — it will not be shown again.",
    )


@router.get("/keys", response_model=ListKeysResponse)
async def list_keys(_key=Depends(admin_auth)):
    """List all API keys. Key hashes and plaintext are never returned."""
    from app.services.key_store import get_key_store
    keys = get_key_store().list_all()
    return ListKeysResponse(
        keys=[ApiKeyInfo(**k.to_dict()) for k in keys],
        total=len(keys),
    )


@router.delete("/keys/{key_id}", response_model=RevokeKeyResponse)
async def revoke_key(key_id: str, _key=Depends(admin_auth)):
    """Revoke a key immediately. Other instances pick up the change within 60s (TTL)."""
    from app.services.key_store import get_key_store
    if not get_key_store().revoke(key_id):
        raise HTTPException(status_code=404, detail=f"Key {key_id!r} not found")
    logger.info("key revoked: %s", key_id)
    return RevokeKeyResponse(status="success", id=key_id, message="Key revoked")


@router.post("/keys/{key_id}/rotate", response_model=RotateKeyResponse)
async def rotate_key(
    key_id: str,
    req: RotateKeyRequest = RotateKeyRequest(),
    _key=Depends(admin_auth),
):
    """
    Issue a replacement key with the same scopes/restrictions.
    Old key remains valid for grace_hours (default 24h) to allow clients to update.
    """
    from app.services.key_store import get_key_store
    try:
        plaintext, new_key, old_expires = get_key_store().rotate(key_id, req.grace_hours)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Key {key_id!r} not found")
    logger.info("key rotated: old=%s new=%s expires=%s", key_id, new_key.id, old_expires)
    return RotateKeyResponse(
        new_key_id=new_key.id, new_key=plaintext,
        old_key_id=key_id, old_key_expires_at=old_expires,
        message="Store this key securely — it will not be shown again.",
    )


@router.post("/reload")
async def reload(_key=Depends(admin_auth)):
    """Force config and key store reload from Secrets Manager."""
    from app.services.key_store import get_key_store
    from config import reload_config
    reload_config()
    get_key_store().reload()
    return {"status": "ok", "message": "Config and key store reloaded"}
```

Note: `include_in_schema=False` on the router hides admin routes from the main `/openapi.json`. They appear only in `/admin/openapi.json` (see Phase 7).

---

## Phase 6: Pre-Authenticated GET Wrapper Endpoints

These live in `app/routes/voatz.py` alongside the existing passthrough endpoints. Existing endpoints (`/get_tokens`, `/get_users`, `/get_events`) are **unchanged**.

### Org restriction helper

```python
def _check_org_access(auth_key, org_id: int):
    """Raise 403 if the key has an org_ids restriction that excludes this org."""
    restricted = getattr(auth_key, "restrictions", {}).get("org_ids")
    if restricted and str(org_id) not in restricted:
        raise HTTPException(
            status_code=403,
            detail="Not authorized for this organization",
        )
```

### New GET endpoints

```python
@router.get("/voatz/users/{org_id}")
async def get_users_wrapped(
    org_id: int,
    auth_key=Depends(read_auth),
):
    """
    Pre-authenticated users endpoint.

    Fetches Voatz tokens from server config — caller needs only a DDP-API
    read key and the org_id. No Voatz credentials required.
    """
    _check_org_access(auth_key, org_id)
    from app.services.voatz import fetch_tokens_from_config, fetch_users
    tokens = fetch_tokens_from_config(org_id)
    users  = fetch_users(tokens["WS"], tokens["Csrf-Token"], org_id)
    return {"status": "success", "users": users}


@router.get("/voatz/events/{org_id}")
async def get_events_wrapped(
    org_id: int,
    limit: Optional[int] = Query(default=None),
    min_ts: Optional[int] = Query(default=None, alias="minTs"),
    auth_key=Depends(read_auth),
):
    """
    Pre-authenticated events endpoint.

    Query params: limit (int), minTs (int)
    """
    _check_org_access(auth_key, org_id)
    from app.services.voatz import fetch_tokens_from_config, fetch_events
    tokens = fetch_tokens_from_config(org_id)
    events = fetch_events(
        tokens["WS"], tokens["Csrf-Token"], org_id,
        limit=limit,
        min_ts=min_ts,
    )
    return {"status": "success", "events": events}
```

---

## Phase 7: Split Docs + `app/main.py` Changes

### Split OpenAPI schemas (Option 2)

Public `/docs` never exposes admin routes. `/admin/docs` is auth-gated by `admin_auth`.

```python
app = FastAPI(
    title="DDP-API",
    description="Digital Democracy Project API — auth gateway and service proxy",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None,       # disable default /docs
    redoc_url=None,      # disable default /redoc
    openapi_url=None,    # disable default /openapi.json
)

# --- Public docs (no admin routes) ---

@app.get("/openapi.json", include_in_schema=False)
async def public_openapi():
    from fastapi.openapi.utils import get_openapi
    return get_openapi(
        title="DDP-API",
        version="2.0.0",
        routes=[r for r in app.routes if not getattr(r, "path", "").startswith("/admin")],
    )

@app.get("/docs", include_in_schema=False)
async def public_docs():
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(openapi_url="/openapi.json", title="DDP-API")

@app.get("/redoc", include_in_schema=False)
async def public_redoc():
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(openapi_url="/openapi.json", title="DDP-API")

# --- Admin docs (admin_auth required) ---

@app.get("/admin/openapi.json", include_in_schema=False)
async def admin_openapi(_key=Depends(admin_auth)):
    from fastapi.openapi.utils import get_openapi
    return get_openapi(
        title="DDP-API Admin",
        version="2.0.0",
        routes=[r for r in app.routes if getattr(r, "path", "").startswith("/admin")],
    )

@app.get("/admin/docs", include_in_schema=False)
async def admin_docs(_key=Depends(admin_auth)):
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(openapi_url="/admin/openapi.json", title="DDP-API Admin")
```

### Flush on shutdown + key store warmup

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.key_store import get_key_store
    get_key_store().reload()          # warm cache on startup
    logger.info("DDP-API started")
    yield
    # Flush in-memory last_used_at back to Secrets Manager before exit
    get_key_store().flush_last_used()
    logger.info("DDP-API shutdown")
```

### Register admin router

```python
from app.routes.admin import router as admin_router
app.include_router(admin_router)
```

---

## Phase 8: Config & IAM Updates

### `config.py` — Python 3.9 test compat

```python
# Before (Python 3.10+ only)
def load_from_secrets_manager() -> dict | None:
def load_from_local_file() -> dict | None:

# After
from typing import Optional
def load_from_secrets_manager() -> Optional[dict]:
def load_from_local_file() -> Optional[dict]:
```

Production (3.10.12) is unaffected. This unblocks the existing test-suite failure.

### IAM policy — add `PutSecretValue`

Required for key issuance, revocation, rotation, and `flush_last_used`. Update the EC2 instance IAM policy before deploying:

```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue",
    "secretsmanager:PutSecretValue"
  ],
  "Resource": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:ddp-api/org-credentials*"
}
```

### `README.md` — key management notes

Add a section covering:
- Revocation latency: up to 60s; use `POST /admin/reload` for immediate invalidation
- `last_used_at` is best-effort — updated in memory and flushed on graceful shutdown only
- Secrets Manager 64KB limit: current design supports ~100+ keys; if volume grows, `api_keys` can move to a dedicated secret
- **Single-worker constraint:** This design assumes a single uvicorn worker. Do not add `--workers` or scale to multiple instances without adding an `asyncio.Lock` around `_secrets_manager_update` in `key_store.py`. Violating this silently introduces a lost-update race on Secrets Manager writes.

### `config.local.example.json` — add `api_keys`

```json
{
  "organizations": [...],
  "api_keys": [
    {
      "id": "key_localdev",
      "name": "Local dev read-only",
      "key_hash": "<sha256 of your test key>",
      "prefix": "ddp-ro",
      "scopes": ["read"],
      "restrictions": {},
      "created_at": "2026-06-17T00:00:00Z",
      "expires_at": null,
      "last_used_at": null
    }
  ]
}
```

---

## Phase 9: Testing Strategy

### Existing tests — unchanged

The env-var fallback path (`API_BEARER_TOKEN`, `API_READ_ONLY_TOKEN`) is preserved. All existing tests in `conftest.py` continue to pass without modification.

### New fixtures in `tests/conftest.py`

```python
@pytest.fixture
def key_store_with_test_keys(tmp_path, monkeypatch):
    """Inject a local config with test keys — no Secrets Manager needed."""
    import hashlib, json

    read_plaintext  = "ddp-ro-testreadkey"
    write_plaintext = "ddp-rw-testwritekey"
    admin_plaintext = "ddp-admin-testadminkey"

    config = {
        "organizations": [
            {"name": "Test Org", "voatz_org_id": 99999,
             "voatz_email": "test@example.com", "voatz_password": "pass"}
        ],
        "api_keys": [
            {
                "id": "key_testread", "name": "Test read",
                "key_hash": hashlib.sha256(read_plaintext.encode()).hexdigest(),
                "prefix": "ddp-ro", "scopes": ["read"], "restrictions": {},
                "created_at": "2026-01-01T00:00:00Z",
                "expires_at": None, "last_used_at": None,
            },
            {
                "id": "key_testwrite", "name": "Test write",
                "key_hash": hashlib.sha256(write_plaintext.encode()).hexdigest(),
                "prefix": "ddp-rw", "scopes": ["read", "write"], "restrictions": {},
                "created_at": "2026-01-01T00:00:00Z",
                "expires_at": None, "last_used_at": None,
            },
            {
                "id": "key_testadmin", "name": "Test admin",
                "key_hash": hashlib.sha256(admin_plaintext.encode()).hexdigest(),
                "prefix": "ddp-admin", "scopes": ["admin"], "restrictions": {},
                "created_at": "2026-01-01T00:00:00Z",
                "expires_at": None, "last_used_at": None,
            },
        ],
    }
    config_file = tmp_path / "config.test.json"
    config_file.write_text(json.dumps(config))
    monkeypatch.setenv("LOCAL_CONFIG_PATH", str(config_file))

    import config as cfg_module
    import app.services.key_store as ks_module
    cfg_module._config   = None
    ks_module._key_store = None
    yield {
        "read":  read_plaintext,
        "write": write_plaintext,
        "admin": admin_plaintext,
    }
    cfg_module._config   = None
    ks_module._key_store = None
```

### New `tests/test_admin.py`

```python
def test_admin_endpoints_require_admin_scope(test_client, key_store_with_test_keys):
    keys = key_store_with_test_keys
    # Read key cannot access admin
    resp = test_client.get("/admin/keys",
        headers={"Authorization": f"Bearer {keys['read']}"})
    assert resp.status_code == 403

    # Write key cannot access admin
    resp = test_client.get("/admin/keys",
        headers={"Authorization": f"Bearer {keys['write']}"})
    assert resp.status_code == 403

def test_issue_key(test_client, key_store_with_test_keys):
    keys = key_store_with_test_keys
    # Admin key can issue
    resp = test_client.post("/admin/keys",
        json={"name": "New key", "scopes": ["read"]},
        headers={"Authorization": f"Bearer {keys['admin']}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"].startswith("ddp-ro-")
    assert "will not be shown again" in body["message"]

def test_issued_key_authenticates(test_client, key_store_with_test_keys):
    keys = key_store_with_test_keys
    issue = test_client.post("/admin/keys",
        json={"name": "Temp", "scopes": ["read"]},
        headers={"Authorization": f"Bearer {keys['admin']}"})
    new_key = issue.json()["key"]
    resp = test_client.get("/health",
        headers={"Authorization": f"Bearer {new_key}"})
    assert resp.status_code == 200

def test_revoke_key(test_client, key_store_with_test_keys):
    keys = key_store_with_test_keys
    issue = test_client.post("/admin/keys",
        json={"name": "To revoke", "scopes": ["read"]},
        headers={"Authorization": f"Bearer {keys['admin']}"})
    key_id = issue.json()["id"]
    resp = test_client.delete(f"/admin/keys/{key_id}",
        headers={"Authorization": f"Bearer {keys['admin']}"})
    assert resp.json()["status"] == "success"

def test_expired_key_rejected(test_client, key_store_with_test_keys):
    keys = key_store_with_test_keys
    issue = test_client.post("/admin/keys",
        json={"name": "Expired", "scopes": ["read"],
              "expires_at": "2020-01-01T00:00:00Z"},
        headers={"Authorization": f"Bearer {keys['admin']}"})
    expired_key = issue.json()["key"]
    resp = test_client.get("/health",
        headers={"Authorization": f"Bearer {expired_key}"})
    assert resp.status_code == 401

def test_org_restricted_key_rejected_for_wrong_org(test_client, key_store_with_test_keys):
    keys = key_store_with_test_keys
    issue = test_client.post("/admin/keys",
        json={"name": "Org restricted", "scopes": ["read"],
              "restrictions": {"org_ids": ["123"]}},
        headers={"Authorization": f"Bearer {keys['admin']}"})
    restricted_key = issue.json()["key"]
    resp = test_client.get("/voatz/users/456",
        headers={"Authorization": f"Bearer {restricted_key}"})
    assert resp.status_code == 403

def test_admin_docs_require_admin_scope(test_client, key_store_with_test_keys):
    keys = key_store_with_test_keys
    # Unauthenticated
    assert test_client.get("/admin/docs").status_code == 403
    # Read key rejected
    assert test_client.get("/admin/docs",
        headers={"Authorization": f"Bearer {keys['read']}"}).status_code == 403
    # Admin key accepted
    assert test_client.get("/admin/docs",
        headers={"Authorization": f"Bearer {keys['admin']}"}).status_code == 200

def test_public_docs_hide_admin_routes(test_client):
    """Explicit CI guard: /openapi.json must never expose /admin paths."""
    resp = test_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    admin_paths = [p for p in paths if p.startswith("/admin")]
    assert admin_paths == [], f"Admin routes leaked into public schema: {admin_paths}"

def test_admin_openapi_requires_auth(test_client):
    assert test_client.get("/admin/openapi.json").status_code == 403

def test_revoke_is_immediate(test_client, key_store_with_test_keys):
    """Revocation must take effect instantly — not after the 60s TTL expires."""
    keys = key_store_with_test_keys
    # Issue a key
    issue = test_client.post("/admin/keys",
        json={"name": "To revoke", "scopes": ["read"]},
        headers={"Authorization": f"Bearer {keys['admin']}"})
    issued_key = issue.json()["key"]
    key_id     = issue.json()["id"]
    # Confirm it works
    assert test_client.get("/health",
        headers={"Authorization": f"Bearer {issued_key}"}).status_code == 200
    # Revoke it
    test_client.delete(f"/admin/keys/{key_id}",
        headers={"Authorization": f"Bearer {keys['admin']}"})
    # Must be rejected immediately — no reload required
    assert test_client.get("/health",
        headers={"Authorization": f"Bearer {issued_key}"}).status_code == 403
```

---

## Phase 10: Migration & Deployment

### Pre-deployment (do before pushing code)

**Step 1 — IAM update**
Add `PutSecretValue` to the EC2 instance IAM role. Without this, key issuance and revocation will fail with `AccessDeniedException`.

**Step 2 — Add `api_keys: []` to Secrets Manager**
Edit the existing secret to add an empty array. The app tolerates an absent or empty `api_keys` field — env-var tokens continue to work during transition.

```bash
# Fetch current secret, add api_keys field, write back
aws secretsmanager get-secret-value --secret-id ddp-api/org-credentials \
  --query SecretString --output text \
  | python3 -c "
import json, sys
s = json.load(sys.stdin)
s.setdefault('api_keys', [])
print(json.dumps(s))
" | aws secretsmanager put-secret-value \
  --secret-id ddp-api/org-credentials \
  --secret-string file:///dev/stdin
```

### Deployment

Confirm the systemd `ExecStart` uses `--workers 1` before restarting:

```ini
ExecStart=/path/to/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5000 --workers 1
```

The key store's Secrets Manager RMW is atomic only within a single uvicorn worker. Adding workers without also adding an `asyncio.Lock` around `_secrets_manager_update` introduces a silent lost-update race.

```bash
git pull origin main
pip install -r requirements.txt   # no new deps
sudo systemctl daemon-reload
sudo systemctl restart ddp-api
sudo systemctl status ddp-api
```

### Post-deployment — bootstrap managed keys

```bash
BASE="https://your-api-domain.com"
WRITE_TOKEN="$API_BEARER_TOKEN"   # existing env-var token for bootstrapping

# Issue a write key for DDP-Sync pipeline
curl -s -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $WRITE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "DDP-Sync pipeline", "scopes": ["read", "write"]}' \
  | python3 -m json.tool

# Issue a read-only key for VoteBot dev, restricted to one org
curl -s -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $WRITE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "VoteBot dev", "scopes": ["read"], "restrictions": {"org_ids": ["800000001"]}}' \
  | python3 -m json.tool

# Issue an admin key for operators
curl -s -X POST $BASE/admin/keys \
  -H "Authorization: Bearer $WRITE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Ops admin", "scopes": ["admin"]}' \
  | python3 -m json.tool
```

**Env-var token deprecation** — once the first admin key is issued and confirmed working, immediately:
1. Issue managed `write` and `read` keys for all active callers (DDP-Sync, VoteBot, etc.)
2. Rotate callers to their new managed keys
3. Remove `API_BEARER_TOKEN` and `API_READ_ONLY_TOKEN` from `.env` and EC2 environment
4. Restart the service — env-var fallback path becomes inert

Do not leave env-var tokens active long-term. They have no expiry, no audit trail, and carry full admin scope.
5. Remove the env-var fallback code path from `app/middleware/auth.py` (the `_EnvVarKey` class and the fallback block in `_resolve`) and ship a follow-up commit. This permanently eliminates the backdoor rather than relying on `.env` hygiene alone.

### Rollback

The env-var fallback is always present. If the key store fails to load (Secrets Manager unreachable, malformed JSON), the app continues to authenticate env-var tokens. No hard dependency on Secrets Manager for basic operation.
