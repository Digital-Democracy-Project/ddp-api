"""Bearer token authentication — key store lookup with env-var fallback.

The key store is the primary auth path. The env-var tokens (API_BEARER_TOKEN,
API_READ_ONLY_TOKEN) remain as a backward-compatible fallback for bootstrapping
and are retired once managed keys are issued to all callers.
"""

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
    """Synthetic key object for env-var token backward compatibility."""
    def __init__(self, scopes: list):
        self.id           = "env-var"
        self.scopes       = scopes
        self.restrictions = {}
        self.expires_at   = None
        self.last_used_at = None


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
        # Track last_used_at in memory; flushed to Secrets Manager on graceful shutdown.
        # best-effort only — SIGKILL/OOM drops in-memory updates.
        key.last_used_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        logger.info("auth key_id=%s name=%r", key.id, key.name)
        return key

    # Env-var fallback — API_BEARER_TOKEN carries full access including admin.
    # Retire these tokens once managed keys are issued to all callers.
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
    """Require write scope. Use on endpoints that mutate data."""
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
    """Require read scope. Write scope also satisfies this check."""
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


# Backward-compatibility alias — write_auth is the correct name for new code
bearer_auth = write_auth
