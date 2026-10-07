"""Admin request/response models for API key management."""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


class IssueKeyRequest(BaseModel):
    name: str
    scopes: list                          # ["read"] | ["write"] | ["admin"] | combinations
    restrictions: Optional[dict] = None   # {"org_ids": [...], "endpoints": [...]}
    environment: Optional[Literal["dev", "prod"]] = None  # independent of restrictions -- see API-5
    expires_at: Optional[str] = None      # ISO 8601 UTC

    # Issuing a key always writes to the key store, so there is no fully
    # inert example (API-7). This one is read-only and already expired, so
    # the key it creates can never authenticate anything.
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"name": "EXAMPLE-DO-NOT-USE", "scopes": ["read"],
         "expires_at": "2000-01-01T00:00:00Z"}
    ]})


class IssueKeyResponse(BaseModel):
    id: str
    key: str                              # plaintext — shown ONCE
    name: str
    scopes: list
    restrictions: Optional[dict]
    environment: Optional[str]
    created_at: str
    expires_at: Optional[str]
    message: str


class ApiKeyInfo(BaseModel):
    id: str
    name: str
    prefix: str
    scopes: list
    restrictions: Optional[dict]
    environment: Optional[str]
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

    model_config = ConfigDict(json_schema_extra={"examples": [{"grace_hours": 24}]})


class RotateKeyResponse(BaseModel):
    new_key_id: str
    new_key: str                          # plaintext — shown ONCE
    old_key_id: str
    old_key_expires_at: str
    message: str
