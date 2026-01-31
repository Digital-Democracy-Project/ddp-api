"""Bearer token authentication middleware."""

import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer_scheme = HTTPBearer()


def get_api_bearer_token() -> str:
    """Get the API bearer token from environment at request time."""
    return os.getenv("API_BEARER_TOKEN", "")


async def bearer_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """
    Validate Bearer token from Authorization header.

    Returns the token if valid, raises HTTPException if invalid.
    """
    api_bearer_token = get_api_bearer_token()

    if not api_bearer_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_BEARER_TOKEN not configured",
        )

    if credentials.credentials != api_bearer_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Bearer token",
        )

    return credentials.credentials
