"""Bearer token authentication middleware."""

import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer_scheme = HTTPBearer()


def _get_write_token() -> str:
    return os.getenv("API_BEARER_TOKEN", "")


def _get_read_only_token() -> str:
    return os.getenv("API_READ_ONLY_TOKEN", "")


async def write_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """
    Validate Bearer token for write access.

    Only accepts API_BEARER_TOKEN. Use on endpoints that mutate data.
    """
    write_token = _get_write_token()

    if not write_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_BEARER_TOKEN not configured",
        )

    if credentials.credentials != write_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Bearer token",
        )

    return credentials.credentials


async def read_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """
    Validate Bearer token for read-only access.

    Accepts either API_BEARER_TOKEN (full access) or API_READ_ONLY_TOKEN.
    Use on endpoints that only read or query data.
    """
    write_token = _get_write_token()
    read_only_token = _get_read_only_token()

    if not write_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_BEARER_TOKEN not configured",
        )

    token = credentials.credentials
    if token == write_token:
        return token
    if read_only_token and token == read_only_token:
        return token

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid Bearer token",
    )


# Backward-compatibility alias — write_auth is the correct name for new code
bearer_auth = write_auth
