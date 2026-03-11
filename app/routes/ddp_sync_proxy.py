"""Catch-all proxy for DDP-Sync service.

All requests to /sync/* and /trigger/* are forwarded to ddp-sync (:8001).
New ddp-sync endpoints are automatically available — no DDP-API code changes needed.
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.middleware.auth import bearer_auth

logger = logging.getLogger(__name__)

router = APIRouter()


DDP_SYNC_SERVICE_URL = "http://localhost:8001"


def _get_ddp_sync_api_key() -> str:
    """Get DDP-Sync API key from Secrets Manager or environment."""
    try:
        from config import get_config
        config = get_config()
        return config.get("ddp_sync_api_key", os.getenv("DDP_SYNC_API_KEY", ""))
    except Exception:
        return os.getenv("DDP_SYNC_API_KEY", "")


async def _forward_to_ddp_sync(request: Request, path: str) -> Response:
    """Forward a request to ddp-sync and return the response."""
    api_key = _get_ddp_sync_api_key()

    # POST sync requests can be long-running (bill batch sync)
    timeout = 300.0 if request.method == "POST" else 30.0

    try:
        async with httpx.AsyncClient(
            base_url=DDP_SYNC_SERVICE_URL,
            timeout=timeout,
        ) as client:
            response = await client.request(
                method=request.method,
                url=f"/ddp-sync/v1/{path}",
                headers={"Authorization": f"Bearer {api_key}"},
                content=await request.body(),
                params=request.query_params,
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )
    except httpx.ConnectError:
        logger.error("Cannot connect to DDP-Sync service")
        raise HTTPException(status_code=502, detail="DDP-Sync service unavailable")
    except httpx.ReadTimeout:
        logger.error("DDP-Sync request timed out")
        raise HTTPException(status_code=504, detail="DDP-Sync request timed out")
    except httpx.RequestError as e:
        logger.error(f"DDP-Sync proxy error: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.api_route(
    "/sync/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
async def proxy_sync(
    request: Request,
    path: str,
    token: str = Depends(bearer_auth),
):
    """Forward all /sync/* requests to ddp-sync."""
    return await _forward_to_ddp_sync(request, f"sync/{path}")


@router.api_route(
    "/trigger/{path:path}",
    methods=["GET", "POST"],
)
async def proxy_trigger(
    request: Request,
    path: str,
    token: str = Depends(bearer_auth),
):
    """Forward all /trigger/* requests to ddp-sync."""
    return await _forward_to_ddp_sync(request, f"trigger/{path}")
