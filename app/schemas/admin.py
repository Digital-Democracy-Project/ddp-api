"""Admin request/response models for API key management."""

from typing import Optional
from pydantic import BaseModel


class IssueKeyRequest(BaseModel):
    name: str
    scopes: list                          # ["read"] | ["write"] | ["admin"] | combinations
    restrictions: Optional[dict] = None   # {"org_ids": [...], "endpoints": [...]}
    expires_at: Optional[str] = None      # ISO 8601 UTC


class IssueKeyResponse(BaseModel):
    id: str
    key: str                              # plaintext — shown ONCE
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
    new_key: str                          # plaintext — shown ONCE
    old_key_id: str
    old_key_expires_at: str
    message: str
