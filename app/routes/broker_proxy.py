"""Catch-all proxy for production ddp-broker-py.

All requests to /broker/* are forwarded verbatim to production ddp-broker-py
(EC2 broker, once it joins the WireGuard mesh) or to a local dev instance
(default). The Mac Studio's ddp-sync instance is not reachable from EC2
broker directly today — this proxy is the relay, mirroring
openstates_proxy.py's own "make an otherwise-unreachable service available"
shape (ddp-infra PLAN-bill-document-provenance.md Phase 8, "Production
write path").

ddp-sync needs zero code changes to use this: pointing its
`ddp_broker_api_base` setting at this proxy's URL makes its existing
`write_bill_artifact()`/`create_concept_statement_set()` calls land here
instead of hitting ddp-broker-py directly — switching environments is a
config change (base URL + token), never a code branch.

Auth: this proxy holds its own downstream credential (a copy of
ddp-broker-py's DDP_SYNC_SERVICE_TOKEN value, not a new secret) rather than
forwarding whatever token the caller presented — ddp-broker-py's
ServiceTokenAuthentication only ever sees this proxy's token, never the
caller's ddp-api key. Inbound calls are gated by the existing
read_auth/write_auth key-store scopes, same as ddp_sync_proxy.py.
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.middleware.auth import read_auth, write_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["broker"])

# This proxy forwards the request body verbatim and validates nothing itself;
# only ddp-broker-py can return a 422. Declaring it here (with no schema)
# suppresses FastAPI's default HTTPValidationError placeholder in the docs.
_NO_VALIDATION_422 = {
    422: {"description": "Not returned by this proxy. Any 422 comes from ddp-broker-py itself."}
}

EC2_BROKER_SERVICE_URL = os.getenv("EC2_BROKER_SERVICE_URL", "http://localhost:8080")


def _get_ddp_broker_api_token() -> str:
    """Get ddp-api's own copy of ddp-broker-py's DDP_SYNC_SERVICE_TOKEN value.

    Same Secrets-Manager-first, env-var-fallback pattern as
    ddp_sync_proxy.py's _get_ddp_sync_api_key() -- a distinct config/env key
    name on this app's side (DDP_BROKER_API_TOKEN), matching the setting name
    ddp-sync's own client already uses for this same shared secret
    (ddp_sync/config.py's `ddp_broker_api_token`).
    """
    try:
        from config import get_config
        config = get_config()
        return config.get("ddp_broker_api_token", os.getenv("DDP_BROKER_API_TOKEN", ""))
    except Exception:
        return os.getenv("DDP_BROKER_API_TOKEN", "")


async def _forward(request: Request, path: str) -> Response:
    """Forward a request to ddp-broker-py and return the response verbatim."""
    token = _get_ddp_broker_api_token()

    try:
        async with httpx.AsyncClient(
            base_url=EC2_BROKER_SERVICE_URL,
            timeout=30.0,
        ) as client:
            response = await client.request(
                method=request.method,
                url=f"/{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": request.headers.get("content-type", "application/json"),
                },
                content=await request.body(),
                params=request.query_params,
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )
    except httpx.ConnectError:
        logger.error("Cannot connect to ddp-broker-py service")
        raise HTTPException(status_code=502, detail="ddp-broker-py service unavailable")
    except httpx.ReadTimeout:
        logger.error("ddp-broker-py request timed out")
        raise HTTPException(status_code=504, detail="ddp-broker-py request timed out")
    except httpx.RequestError as e:
        logger.error(f"ddp-broker-py proxy error: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get(
    "/broker/{path:path}",
    operation_id="proxy_broker_read",
    summary="Forward a read to ddp-broker-py",
    responses=_NO_VALIDATION_422,
)
async def proxy_broker_read(
    request: Request,
    path: str,
    token: str = Depends(read_auth),
):
    """Forward GET /broker/* requests to ddp-broker-py (read-only token accepted)."""
    return await _forward(request, path)


@router.post(
    "/broker/{path:path}",
    operation_id="proxy_broker_create",
    summary="Forward a write to ddp-broker-py",
    responses=_NO_VALIDATION_422,
)
@router.put(
    "/broker/{path:path}",
    operation_id="proxy_broker_replace",
    summary="Forward a write to ddp-broker-py",
    responses=_NO_VALIDATION_422,
)
@router.delete(
    "/broker/{path:path}",
    operation_id="proxy_broker_delete",
    summary="Forward a delete to ddp-broker-py",
    responses=_NO_VALIDATION_422,
)
async def proxy_broker_write(
    request: Request,
    path: str,
    token: str = Depends(write_auth),
):
    """Forward POST/PUT/DELETE /broker/* requests to ddp-broker-py (write token required)."""
    return await _forward(request, path)
