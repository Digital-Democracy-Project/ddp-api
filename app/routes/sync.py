"""Sync job trigger endpoint."""

import logging
from fastapi import APIRouter, HTTPException, Depends

from app.middleware.auth import bearer_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


@router.post("/trigger_sync")
async def trigger_sync(token: str = Depends(bearer_auth)):
    """Manually trigger the user sync job."""
    try:
        from scheduler import run_sync_job

        run_sync_job()
        return {"status": "success", "message": "Sync job triggered"}
    except Exception as e:
        logger.error(f"Manual sync trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
