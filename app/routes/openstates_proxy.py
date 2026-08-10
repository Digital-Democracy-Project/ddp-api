"""Catch-all proxy for DDP's own self-hosted OpenStates api-v3 instance.

This is DDP's own fork of openstates/api-v3, running DDP's own scrapers
against DDP's own database on the Mac Studio (10.0.0.8:8002, over
WireGuard) -- it reuses api-v3's schema/codebase but is NOT the public
openstates.org API and holds no upstream openstates.org data. The Mac
Studio is not reachable from all EC2 instances directly -- this proxy
makes it available to services (e.g. ddp-broker-py) that don't have
WireGuard configured.

Auth: standard ddp-api bearer token (same as every other route).
The local UUID key is injected when forwarding to api-v3 internally.
"""

import asyncio
import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.middleware.auth import read_auth, write_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ddp-openstates"])

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

# OPEN-39: a bare ConnectError (WireGuard blip, api-v3 container mid-restart) is usually
# gone within a second -- one bounded retry absorbs that without turning a routine restart
# into a hard failure for the caller. Anything past this is a real outage; escalate as before.
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 0.5


async def _forward(request: Request, path: str) -> Response:
    # Strip any incoming apikey param — callers authenticate via the ddp-api bearer token.
    # Must stay a list of (key, value) tuples, not a dict: query strings like
    # ?include=votes&include=actions carry multiple values under the same key, and a
    # dict comprehension would silently keep only the last one, dropping the rest
    # before the request ever reaches api-v3 (API-1).
    params = [(k, v) for k, v in request.query_params.multi_items() if k != "apikey"]
    body = await request.body()
    headers = {
        "Content-Type": request.headers.get("content-type", "application/json"),
        "x-api-key": _OPENSTATES_INTERNAL_KEY,
    }

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(base_url=OPENSTATES_SERVICE_URL, timeout=30.0) as client:
                response = await client.request(
                    method=request.method,
                    url=f"/{path}",
                    params=params,
                    headers=headers,
                    content=body,
                )
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )
        except httpx.ConnectError:
            if attempt < _MAX_ATTEMPTS:
                logger.warning(
                    "ConnectError reaching OpenStates api-v3 (attempt %d/%d) — retrying once",
                    attempt, _MAX_ATTEMPTS,
                )
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
                continue
            logger.error(
                "Cannot connect to OpenStates api-v3 at %s (after %d attempts)",
                OPENSTATES_SERVICE_URL, _MAX_ATTEMPTS,
            )
            raise HTTPException(status_code=502, detail="OpenStates api-v3 unavailable")
        except httpx.ReadTimeout:
            raise HTTPException(status_code=504, detail="OpenStates api-v3 timed out")
        except httpx.RequestError as e:
            logger.error("OpenStates proxy error: %s", e)
            raise HTTPException(status_code=502, detail=str(e))


# OPEN-39 AC1: declared ahead of the GET catch-all below so Starlette's order-based route
# matching resolves this exact path first. Deliberately unauthenticated -- external end-to-end
# monitoring (ddp-agents' health-monitor) needs to probe the full ddp-api -> WireGuard -> api-v3
# path without holding a ddp-api bearer token just for a liveness check. Shares _forward()'s
# retry/error-mapping so a probe hit gets the exact same resilience real traffic gets.
@router.get(
    "/openstates/healthz",
    operation_id="proxy_openstates_healthz",
    summary="Unauthenticated liveness passthrough for DDP's OpenStates instance",
)
async def proxy_openstates_healthz(request: Request):
    """Unauthenticated end-to-end liveness check: forwards to api-v3's own /healthz over the
    same path production reads use (ddp-api -> WireGuard -> api-v3), so a proxy/token/tunnel
    failure shows up here even when api-v3 itself is healthy."""
    return await _forward(request, "healthz")


@router.get(
    "/openstates/{path:path}",
    operation_id="proxy_openstates_read",
    summary="Forward a read to DDP's own OpenStates instance",
    responses=_NO_VALIDATION_422,
)
async def proxy_openstates_read(
    request: Request,
    path: str,
    token: str = Depends(read_auth),
):
    """Forward GET /openstates/* requests to DDP's own self-hosted OpenStates api-v3 instance
    (read-only token accepted) — DDP's own scraped data, not the public openstates.org API."""
    return await _forward(request, path)


@router.post(
    "/openstates/{path:path}",
    operation_id="proxy_openstates_write",
    summary="Forward a write to DDP's own OpenStates instance",
    responses=_NO_VALIDATION_422,
)
async def proxy_openstates_write(
    request: Request,
    path: str,
    token: str = Depends(write_auth),
):
    """Forward POST /openstates/* requests to DDP's own self-hosted OpenStates api-v3 instance
    (write token required) — DDP's own scraped data, not the public openstates.org API."""
    return await _forward(request, path)
