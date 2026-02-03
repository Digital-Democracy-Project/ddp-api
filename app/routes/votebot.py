"""VoteBot proxy endpoints."""

import asyncio
import logging
import os
from typing import Optional

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.middleware.auth import bearer_auth
from config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/votebot", tags=["votebot"])


def get_votebot_config() -> dict:
    """Get VoteBot configuration from config or environment."""
    try:
        config = get_config()
        return {
            "service_url": config.get(
                "votebot_service_url",
                os.getenv("VOTEBOT_SERVICE_URL", "http://localhost:8000"),
            ),
            "ws_url": config.get(
                "votebot_ws_url",
                os.getenv("VOTEBOT_WS_URL", "ws://localhost:8000/ws/chat"),
            ),
            "api_key": config.get(
                "votebot_api_key",
                os.getenv("VOTEBOT_API_KEY", ""),
            ),
        }
    except Exception:
        # Fallback to environment variables if config loading fails
        return {
            "service_url": os.getenv("VOTEBOT_SERVICE_URL", "http://localhost:8000"),
            "ws_url": os.getenv("VOTEBOT_WS_URL", "ws://localhost:8000/ws/chat"),
            "api_key": os.getenv("VOTEBOT_API_KEY", ""),
        }


@router.post("/chat")
async def votebot_chat(
    request: dict,
    token: str = Depends(bearer_auth),
):
    """
    Proxy chat requests to VoteBot service.

    Request body should contain:
    - message: str
    - session_id: str
    - page_context: optional dict with type, url, title, etc.
    """
    config = get_votebot_config()

    async with httpx.AsyncClient(
        base_url=config["service_url"],
        headers={"Authorization": f"Bearer {config['api_key']}"},
        timeout=60.0,
    ) as client:
        try:
            response = await client.post("/votebot/v1/chat", json=request)

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text,
                )

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"VoteBot chat request failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"VoteBot service unavailable: {e}",
            )


@router.post("/chat/stream")
async def votebot_chat_stream(
    request: dict,
    token: str = Depends(bearer_auth),
):
    """
    Proxy streaming chat requests to VoteBot service with SSE passthrough.

    Request body should contain:
    - message: str
    - session_id: str
    - page_context: optional dict with type, url, title, etc.
    """
    config = get_votebot_config()

    async def stream_generator():
        async with httpx.AsyncClient(
            base_url=config["service_url"],
            headers={"Authorization": f"Bearer {config['api_key']}"},
            timeout=120.0,
        ) as client:
            try:
                async with client.stream(
                    "POST",
                    "/votebot/v1/chat/stream",
                    json=request,
                ) as response:
                    if response.status_code >= 400:
                        error_text = await response.aread()
                        yield f"data: {{'error': '{error_text.decode()}'}}\n\n"
                        return

                    async for chunk in response.aiter_bytes():
                        yield chunk

            except httpx.RequestError as e:
                logger.error(f"VoteBot stream request failed: {e}")
                yield f"data: {{'error': 'VoteBot service unavailable: {e}'}}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback")
async def votebot_feedback(
    request: dict,
    token: str = Depends(bearer_auth),
):
    """
    Proxy feedback submissions to VoteBot service.

    Request body should contain:
    - session_id: str
    - message_id: str
    - feedback_type: str ("positive" or "negative")
    - feedback_text: optional str
    """
    config = get_votebot_config()

    async with httpx.AsyncClient(
        base_url=config["service_url"],
        headers={"Authorization": f"Bearer {config['api_key']}"},
        timeout=30.0,
    ) as client:
        try:
            response = await client.post("/votebot/v1/chat/feedback", json=request)

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text,
                )

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"VoteBot feedback request failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"VoteBot service unavailable: {e}",
            )


@router.post("/sync/bill")
async def votebot_sync_bill(
    request: dict,
    token: str = Depends(bearer_auth),
):
    """
    Proxy bill sync requests to VoteBot service.

    Request body should contain:
    - webflow_item_id: str (primary identifier)
    - slug: str (fallback identifier)
    """
    config = get_votebot_config()

    async with httpx.AsyncClient(
        base_url=config["service_url"],
        headers={"Authorization": f"Bearer {config['api_key']}"},
        timeout=120.0,  # Sync can take a while
    ) as client:
        try:
            response = await client.post("/votebot/v1/sync/bill", json=request)

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text,
                )

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"VoteBot bill sync request failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"VoteBot service unavailable: {e}",
            )


@router.post("/sync/legislator")
async def votebot_sync_legislator(
    request: dict,
    token: str = Depends(bearer_auth),
):
    """
    Proxy legislator sync requests to VoteBot service.

    Request body should contain:
    - webflow_item_id: str (primary identifier)
    - slug: str (fallback identifier)
    """
    config = get_votebot_config()

    async with httpx.AsyncClient(
        base_url=config["service_url"],
        headers={"Authorization": f"Bearer {config['api_key']}"},
        timeout=120.0,  # Sync can take a while
    ) as client:
        try:
            response = await client.post("/votebot/v1/sync/legislator", json=request)

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text,
                )

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"VoteBot legislator sync request failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"VoteBot service unavailable: {e}",
            )


@router.post("/sync/organization")
async def votebot_sync_organization(
    request: dict,
    token: str = Depends(bearer_auth),
):
    """
    Proxy organization sync requests to VoteBot service.

    Request body should contain:
    - webflow_item_id: str (primary identifier)
    - slug: str (fallback identifier)
    """
    config = get_votebot_config()

    async with httpx.AsyncClient(
        base_url=config["service_url"],
        headers={"Authorization": f"Bearer {config['api_key']}"},
        timeout=120.0,  # Sync can take a while
    ) as client:
        try:
            response = await client.post("/votebot/v1/sync/organization", json=request)

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text,
                )

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"VoteBot organization sync request failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"VoteBot service unavailable: {e}",
            )


@router.post("/sync/unified")
async def votebot_sync_unified(
    request: dict,
    token: str = Depends(bearer_auth),
):
    """
    Proxy unified sync requests to VoteBot service.

    Request body should contain:
    - content_type: str ("bill", "legislator", "organization", "webpage", "training")
    - mode: str ("single" or "batch")
    - webflow_id: optional str
    - slug: optional str
    - include_pdfs: optional bool
    - include_openstates: optional bool
    - dry_run: optional bool
    """
    config = get_votebot_config()

    async with httpx.AsyncClient(
        base_url=config["service_url"],
        headers={"Authorization": f"Bearer {config['api_key']}"},
        timeout=300.0,  # Unified sync can take longer
    ) as client:
        try:
            response = await client.post("/votebot/v1/sync/unified", json=request)

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text,
                )

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"VoteBot unified sync request failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"VoteBot service unavailable: {e}",
            )


@router.websocket("/ws")
async def votebot_websocket(
    websocket: WebSocket,
    session_id: Optional[str] = Query(default=None),
):
    """
    WebSocket proxy to VoteBot service.

    Establishes a bidirectional WebSocket connection, forwarding messages
    between the client and the VoteBot service.

    Query params:
    - session_id: optional session ID to resume a conversation
    """
    await websocket.accept()

    config = get_votebot_config()
    votebot_ws_url = config["ws_url"]
    if session_id:
        votebot_ws_url += f"?session_id={session_id}"

    try:
        # Connect to VoteBot WebSocket
        async with websockets.connect(
            votebot_ws_url,
            additional_headers={"Authorization": f"Bearer {config['api_key']}"},
        ) as votebot_ws:

            async def client_to_votebot():
                """Forward messages from client to VoteBot."""
                try:
                    async for message in websocket.iter_text():
                        await votebot_ws.send(message)
                except WebSocketDisconnect:
                    pass

            async def votebot_to_client():
                """Forward messages from VoteBot to client."""
                try:
                    async for message in votebot_ws:
                        await websocket.send_text(message)
                except websockets.exceptions.ConnectionClosed:
                    pass

            # Run both directions concurrently
            await asyncio.gather(
                client_to_votebot(),
                votebot_to_client(),
                return_exceptions=True,
            )

    except WebSocketDisconnect:
        logger.debug("Client WebSocket disconnected")
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"VoteBot WebSocket connection failed: {e}")
        await websocket.close(code=1011, reason="VoteBot service unavailable")
    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
        await websocket.close(code=1011, reason=str(e))
