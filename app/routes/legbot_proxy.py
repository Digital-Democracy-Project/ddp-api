"""Proxy for on-demand LegBot analyze_bill dispatch (API-4).

Gives ddp-next a way to trigger an on-demand LegBot analyze_bill task from a
public-facing UX (e.g. "explain this bill" / "pros and cons" on a bill
page) -- distinct from ddp-sync's existing scheduled batch generation
(SYNC-9). No new CAMS-side dispatch code is needed: this hits the exact same
generic task API (bot="legbot", task_type="analyze_bill") that ddp-agents'
own dispatch_legbot tool and ddp-sync's legbot_client.py already use.

Unlike ddp_sync_proxy.py/openstates_proxy.py/broker_proxy.py, this is NOT a
blind catch-all -- bot/task_type are injected here, server-side, rather than
trusted from the caller. That's deliberate: this route should only ever be
able to produce legbot/analyze_bill tasks on CAMS, never dispatch arbitrary
bots/task_types through to it.

Async dispatch-and-poll, not synchronous request-response: POST /legbot/tasks
returns as soon as CAMS queues the task (it does not wait on the MLX
response -- MLX cold-start can take up to ~90s and requests may queue behind
legbot/reasoning.py's asyncio.Semaphore(1), which is accepted as-is for
launch). ddp-next dispatches, shows an "analyzing..." state, and polls
GET /legbot/tasks/{task_id} the way get_task_artifacts/task_result.json
already work for CAMS's other callers.

Known gap (flagged during planning, not fixed here): CAMS's task-status
endpoint below currently returns only {"status": ...} -- the actual answer
lives in CAMS's local artifacts/{task_id}/task_result.json, read directly
off the filesystem by ddp-sync's legbot_client.py and Agent Smith's own
get_task_artifacts, both of which run on the same box as CAMS. ddp-api runs
on EC2, not the Mac Studio, so it cannot read that file today. The GET route
below forwards CAMS's response verbatim rather than guessing at a shape, so
whenever CAMS is extended to expose the result over HTTP, ddp-next picks it
up with zero ddp-api code changes -- same "downstream adds a capability, the
proxy doesn't need to change" pattern as the other three proxies in this
directory.
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.middleware.auth import read_auth, write_auth
from app.schemas.legbot import LegBotAnalyzeRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["legbot"])

CAMS_SERVICE_URL = os.getenv("CAMS_SERVICE_URL", "http://10.0.0.8:8000")

# The caller identity CAMS/LegBot records for this dispatch path, matching
# ddp-sync's legbot_client.py convention of stamping its own "caller" value
# ("ddp_sync") into the payload -- this route's callers are ddp-next users.
_CALLER = "ddp_next"


def _get_cams_api_token() -> str:
    """Get ddp-api's own copy of CAMS's shared bearer token.

    Same Secrets-Manager-first, env-var-fallback pattern as
    broker_proxy.py's _get_ddp_broker_api_token() -- a distinct config/env
    key name on this app's side (CAMS_API_TOKEN), matching the setting name
    ddp-sync's own client already uses for this same shared secret
    (ddp_sync/config.py's `cams_api_token`).
    """
    try:
        from config import get_config
        config = get_config()
        return config.get("cams_api_token", os.getenv("CAMS_API_TOKEN", ""))
    except Exception:
        return os.getenv("CAMS_API_TOKEN", "")


async def _forward_to_cams(method: str, path: str, request: Request, json_body=None) -> Response:
    """Forward a request to CAMS and return the response verbatim."""
    token = _get_cams_api_token()

    try:
        async with httpx.AsyncClient(base_url=CAMS_SERVICE_URL, timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=f"/{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=request.query_params,
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )
    except httpx.ConnectError:
        logger.error("Cannot connect to CAMS service")
        raise HTTPException(status_code=502, detail="CAMS service unavailable")
    except httpx.ReadTimeout:
        logger.error("CAMS request timed out")
        raise HTTPException(status_code=504, detail="CAMS request timed out")
    except httpx.RequestError as e:
        logger.error(f"CAMS proxy error: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.post(
    "/legbot/tasks",
    operation_id="legbot_dispatch_analyze_bill",
    summary="Dispatch an on-demand LegBot analyze_bill task",
)
async def legbot_dispatch_analyze_bill(
    req: LegBotAnalyzeRequest,
    request: Request,
    token: str = Depends(write_auth),
):
    """Dispatch an analyze_bill task to CAMS/LegBot (write token required).

    bot="legbot" and task_type="analyze_bill" are fixed here, not caller-
    supplied. Returns CAMS's create-task response verbatim (a task_id) as
    soon as the task is queued -- it does not wait for MLX to answer.
    """
    payload = req.model_dump()
    payload["caller"] = _CALLER
    cams_body = {"bot": "legbot", "task_type": "analyze_bill", "payload": payload}
    return await _forward_to_cams("POST", "api/v1/tasks", request, json_body=cams_body)


@router.get(
    "/legbot/tasks/{task_id}",
    operation_id="legbot_get_task_status",
    summary="Poll an on-demand LegBot task's status",
)
async def legbot_get_task_status(
    task_id: str,
    request: Request,
    token: str = Depends(read_auth),
):
    """Poll a dispatched LegBot task's status (read-only token accepted).

    Forwards CAMS's response verbatim -- see the module docstring's "Known
    gap" note about the result itself not yet being exposed here.
    """
    return await _forward_to_cams("GET", f"api/v1/tasks/{task_id}", request)
