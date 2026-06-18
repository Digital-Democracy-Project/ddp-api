"""In-memory API key store backed by AWS Secrets Manager.

Concurrency model: _secrets_manager_update uses synchronous boto3 intentionally.
Synchronous boto3 calls block the entire asyncio event loop thread, so no other
coroutine can interleave during the get→modify→put sequence — making RMW
effectively atomic within a single uvicorn worker.

IMPORTANT: This design assumes a single uvicorn worker (--workers 1). Adding
workers or scaling to multiple instances without adding an asyncio.Lock around
_secrets_manager_update will introduce a silent lost-update race on Secrets
Manager writes. If this is ever refactored to use aiobotocore (async boto3),
an asyncio.Lock must be added for the same reason.
"""

import hashlib
import json
import logging
import os
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
            "id":           self.id,
            "name":         self.name,
            "key_hash":     self.key_hash,
            "prefix":       self.prefix,
            "scopes":       self.scopes,
            "restrictions": self.restrictions,
            "created_at":   self.created_at,
            "expires_at":   self.expires_at,
            "last_used_at": self.last_used_at,
        }


class KeyStore:
    def __init__(self):
        self._lock      = threading.Lock()
        self._by_hash   = {}   # key_hash -> ApiKey
        self._by_id     = {}   # key_id   -> ApiKey
        self._loaded_at = None

    def _load_from_config(self):
        try:
            from config import get_config
            config = get_config()
        except RuntimeError as e:
            # No Secrets Manager access and no local config file — start empty.
            # Auth falls back to env-var tokens (API_BEARER_TOKEN / API_READ_ONLY_TOKEN).
            logger.warning("Key store: config unavailable (%s) — starting with empty key list", e)
            with self._lock:
                self._by_hash   = {}
                self._by_id     = {}
                self._loaded_at = datetime.now(timezone.utc)
            return
        by_hash, by_id = {}, {}
        for entry in config.get("api_keys", []):
            key = ApiKey(entry)
            by_hash[key.key_hash] = key
            by_id[key.id]         = key
        with self._lock:
            self._by_hash   = by_hash
            self._by_id     = by_id
            self._loaded_at = datetime.now(timezone.utc)
        logger.info("Key store loaded: %d keys", len(by_id))

    def _maybe_refresh(self):
        if self._loaded_at is None:
            self._load_from_config()
            return
        age = (datetime.now(timezone.utc) - self._loaded_at).total_seconds()
        if age > CACHE_TTL_SECONDS:
            self._load_from_config()

    def reload(self):
        """Force full reload from config source."""
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
        """Generate a new key, persist to config source, update cache. Returns (plaintext, ApiKey)."""
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
            "id":           key_id,
            "name":         name,
            "key_hash":     key_hash,
            "prefix":       prefix,
            "scopes":       scopes,
            "restrictions": restrictions or {},
            "created_at":   now,
            "expires_at":   expires_at,
            "last_used_at": None,
        }
        key = ApiKey(entry)
        _persist_update(lambda keys: keys + [entry])
        with self._lock:
            self._by_hash[key_hash] = key
            self._by_id[key_id]     = key
        logger.info("Key issued: id=%s name=%r scopes=%s", key_id, name, scopes)
        return plaintext, key

    def revoke(self, key_id: str) -> bool:
        """Remove a key by ID. Effective immediately in this process. Returns False if not found."""
        with self._lock:
            key = self._by_id.pop(key_id, None)
            if not key:
                return False
            self._by_hash.pop(key.key_hash, None)
        _persist_update(lambda keys: [k for k in keys if k["id"] != key_id])
        logger.info("Key revoked: id=%s", key_id)
        return True

    def rotate(self, key_id: str, grace_hours: int = 24) -> tuple:
        """
        Issue a replacement key with the same scopes/restrictions.
        Set expires_at on the old key for the grace window.
        Returns (new_plaintext, new_ApiKey, old_expires_at_str).
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

        # Set expiry on old key in memory and persisted store
        with self._lock:
            if key_id in self._by_id:
                self._by_id[key_id].expires_at = expires

        _persist_update(
            lambda keys: [
                {**k, "expires_at": expires} if k["id"] == key_id else k
                for k in keys
            ]
        )
        logger.info("Key rotated: old=%s new=%s grace_hours=%d", key_id, new_key.id, grace_hours)
        return plaintext, new_key, expires

    def flush_last_used(self):
        """
        Write in-memory last_used_at values back to the config source.
        Called on graceful shutdown. last_used_at is a best-effort metric —
        SIGKILL or OOM kills will drop any in-memory updates since the last flush.
        """
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
            _persist_update(_update)
            logger.info("Flushed last_used_at for %d keys", len(in_memory))
        except Exception as e:
            logger.error("Failed to flush last_used_at: %s", e)


def _persist_update(transform):
    """
    Read-modify-write: apply transform to the api_keys list and persist.

    Tries AWS Secrets Manager first (production). Falls back to the local
    config file (development / tests). Mirrors the load strategy in config.py.

    Uses synchronous boto3 intentionally — see module docstring for concurrency
    model and the asyncio.Lock requirement if ever refactored to async.
    """
    from config import AWS_SECRET_NAME, AWS_REGION, LOCAL_CONFIG_PATH

    # --- Production: AWS Secrets Manager ---
    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, ClientError

        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        resp   = client.get_secret_value(SecretId=AWS_SECRET_NAME)
        secret = json.loads(resp["SecretString"])
        secret["api_keys"] = transform(secret.get("api_keys", []))
        client.put_secret_value(
            SecretId=AWS_SECRET_NAME,
            SecretString=json.dumps(secret),
        )
        return
    except (NoCredentialsError, ClientError) as e:
        logger.warning("Secrets Manager unavailable, falling back to local file: %s", e)
    except Exception as e:
        logger.warning("Secrets Manager update failed, falling back to local file: %s", e)

    # --- Development: local config file ---
    if not os.path.exists(LOCAL_CONFIG_PATH):
        raise RuntimeError(
            f"Cannot persist key store: Secrets Manager unavailable and "
            f"no local config file at {LOCAL_CONFIG_PATH!r}"
        )
    with open(LOCAL_CONFIG_PATH) as f:
        secret = json.load(f)
    secret["api_keys"] = transform(secret.get("api_keys", []))
    with open(LOCAL_CONFIG_PATH, "w") as f:
        json.dump(secret, f, indent=2)


_key_store: Optional[KeyStore] = None


def get_key_store() -> KeyStore:
    global _key_store
    if _key_store is None:
        _key_store = KeyStore()
    return _key_store
