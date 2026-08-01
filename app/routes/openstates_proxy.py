"""Catch-all proxy for the local OpenStates api-v3 instance.

All requests to /openstates/* are forwarded to the Mac Studio api-v3
(10.0.0.8:8002) over WireGuard. The Mac Studio is not reachable from
all EC2 instances directly — this proxy makes it available to services
(e.g. ddp-broker-py) that don't have WireGuard configured.

Auth: standard ddp-api bearer token (same as every other route).
The local UUID key is injected when forwarding to api-v3 internally.
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.middleware.auth import read_auth, write_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openstates"])

# This proxy forwards the request body verbatim and validates nothing itself;
# only api-v3 can return a 422. Declaring it here (with no schema) suppresses
# FastAPI's default HTTPValidationError placeholder in the generated docs.
_NO_VALIDATION_422 = {
    422: {"description": "Not returned by this proxy. Any 422 comes from api-v3 itself."}
}

OPENSTATES_SERVICE_URL = os.getenv("OPENSTATES_SERVICE_URL", "http://10.0.0.8:8002")
# Internal UUID key for the local api-v3 instance. Not a secret — only reachable
# over WireGuard. Sent as x-api-key header so callers never need to supply it.
_OPENSTATES_INTERNAL_KEY = "00000000-0000-0000-0000-000000000001"


async def _forward(request: Request, path: str) -> Response:
    # Strip any incoming apikey param — callers authenticate via the ddp-api bearer token
    params = {k: v for k, v in request.query_params.items() if k != "apikey"}

    try:
        async with httpx.AsyncClient(base_url=OPENSTATES_SERVICE_URL, timeout=30.0) as client:
            response = await client.request(
                method=request.method,
                url=f"/{path}",
                params=params,
                headers={
                    "Content-Type": request.headers.get("content-type", "application/json"),
                    "x-api-key": _OPENSTATES_INTERNAL_KEY,
                },
                content=await request.body(),
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )
    except httpx.ConnectError:
        logger.error("Cannot connect to OpenStates api-v3 at %s", OPENSTATES_SERVICE_URL)
        raise HTTPException(status_code=502, detail="OpenStates api-v3 unavailable")
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail="OpenStates api-v3 timed out")
    except httpx.RequestError as e:
        logger.error("OpenStates proxy error: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get(
    "/openstates/{path:path}",
    operation_id="proxy_openstates_read",
    summary="Forward a read to the local OpenStates api-v3",
    responses=_NO_VALIDATION_422,
)
async def proxy_openstates_read(
    request: Request,
    path: str,
    token: str = Depends(read_auth),
):
    """Forward GET /openstates/* requests to the local api-v3 instance (read-only token accepted)."""
    return await _forward(request, path)


@router.post(
    "/openstates/{path:path}",
    operation_id="proxy_openstates_write",
    summary="Forward a write to the local OpenStates api-v3",
    responses=_NO_VALIDATION_422,
)
async def proxy_openstates_write(
    request: Request,
    path: str,
    token: str = Depends(write_auth),
):
    """Forward POST /openstates/* requests to the local api-v3 instance (write token required)."""
    return await _forward(request, path)
