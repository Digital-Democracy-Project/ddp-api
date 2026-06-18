"""Admin endpoints for API key management.

All endpoints require admin_auth. This router is registered with
include_in_schema=False so admin routes never appear in the public /docs.
They are documented separately at /admin/docs (also admin_auth protected).
"""

import logging
from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import admin_auth
from app.schemas.admin import (
    ApiKeyInfo,
    IssueKeyRequest,
    IssueKeyResponse,
    ListKeysResponse,
    RevokeKeyResponse,
    RotateKeyRequest,
    RotateKeyResponse,
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
        id=key.id,
        key=plaintext,
        name=key.name,
        scopes=key.scopes,
        restrictions=key.restrictions,
        created_at=key.created_at,
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
    """Revoke a key. Effective immediately in this process; other instances pick up within 60s."""
    from app.services.key_store import get_key_store
    if not get_key_store().revoke(key_id):
        raise HTTPException(status_code=404, detail=f"Key {key_id!r} not found")
    return RevokeKeyResponse(status="success", id=key_id, message="Key revoked")


@router.post("/keys/{key_id}/rotate", response_model=RotateKeyResponse)
async def rotate_key(
    key_id: str,
    req: RotateKeyRequest = RotateKeyRequest(),
    _key=Depends(admin_auth),
):
    """
    Issue a replacement key with the same scopes/restrictions.
    The old key remains valid for grace_hours (default 24h) to allow clients to update.
    The new plaintext is shown exactly once — store it securely.
    """
    from app.services.key_store import get_key_store
    try:
        plaintext, new_key, old_expires = get_key_store().rotate(key_id, req.grace_hours)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Key {key_id!r} not found")
    return RotateKeyResponse(
        new_key_id=new_key.id,
        new_key=plaintext,
        old_key_id=key_id,
        old_key_expires_at=old_expires,
        message="Store this key securely — it will not be shown again.",
    )


@router.post("/reload")
async def reload(_key=Depends(admin_auth)):
    """Force config and key store reload from Secrets Manager. Also clears the 60s TTL cache."""
    from app.services.key_store import get_key_store
    from config import reload_config
    reload_config()
    get_key_store().reload()
    return {"status": "ok", "message": "Config and key store reloaded"}
