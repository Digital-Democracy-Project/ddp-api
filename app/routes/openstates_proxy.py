"""Catch-all proxy for the local OpenStates api-v3 instance.

All requests to /openstates/* are forwarded to the Mac Studio api-v3
(10.0.0.8:8002) over WireGuard. The Mac Studio is not reachable from
all EC2 instances directly — this proxy makes it available to services
(e.g. ddp-broker-py) that don't have WireGuard configured.

Auth: accepts the configured OPENSTATES_PROXY_KEY as either an
  ?apikey=<key> query parameter (ddp-broker-py's native format) or
  an Authorization: Bearer <key> header. Forwards the UUID key to
  api-v3 so api-v3's own auth is also satisfied.
"""

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()

OPENSTATES_SERVICE_URL = os.getenv("OPENSTATES_SERVICE_URL", "http://10.0.0.8:8002")
OPENSTATES_PROXY_KEY   = os.getenv("OPENSTATES_PROXY_KEY", "00000000-0000-0000-0000-000000000001")


def _check_auth(request: Request, apikey: Optional[str]) -> None:
    """Accept the proxy key as ?apikey= or Authorization: Bearer."""
    bearer = request.headers.get("Authorization", "")
    if bearer.startswith("Bearer "):
        bearer = bearer[7:]
    provided = apikey or bearer
    if provided != OPENSTATES_PROXY_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def _forward(request: Request, path: str, apikey: Optional[str]) -> Response:
    _check_auth(request, apikey)

    # Always send the local UUID key to api-v3 regardless of what came in
    params = dict(request.query_params)
    params["apikey"] = OPENSTATES_PROXY_KEY

    timeout = 30.0
    try:
        async with httpx.AsyncClient(
            base_url=OPENSTATES_SERVICE_URL,
            timeout=timeout,
        ) as client:
            response = await client.request(
                method=request.method,
                url=f"/{path}",
                params=params,
                headers={"Content-Type": request.headers.get("content-type", "application/json")},
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


@router.api_route("/openstates/{path:path}", methods=["GET", "POST"])
async def proxy_openstates(
    request: Request,
    path: str,
    apikey: Optional[str] = Query(default=None),
):
    """Forward all /openstates/* requests to the local api-v3 instance."""
    return await _forward(request, path, apikey)
