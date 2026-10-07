"""Admin request/response models for API key management."""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, field_validator

# The name pre-filled on /admin/docs. A key request using it is refused, so
# clicking Execute on the unmodified example saves nothing (API-8).
EXAMPLE_KEY_NAME = "EXAMPLE-DO-NOT-USE"


class IssueKeyRequest(BaseModel):
    name: str
    scopes: list                          # ["read"] | ["write"] | ["admin"] | combinations
    restrictions: Optional[dict] = None   # {"org_ids": [...], "endpoints": [...]}
    environment: Optional[Literal["dev", "prod"]] = None  # independent of restrictions -- see API-5
    expires_at: Optional[str] = None      # ISO 8601 UTC

    @field_validator("name")
    @classmethod
    def _refuse_example_name(cls, name: str) -> str:
        if name.strip() == EXAMPLE_KEY_NAME:
            raise ValueError(
                f"{EXAMPLE_KEY_NAME!r} is the placeholder name from the docs example. "
                "No key was created. Use a real name to issue a key."
            )
        return name

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"name": EXAMPLE_KEY_NAME, "scopes": ["read"]}
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
