"""
DDP-API FastAPI Application.

This application acts as a proxy server to receive API requests and forward
them to the Voatz API, routed through the Digital Democracy Project EC2 instance
which has a white-labeled IP address with Voatz.

The app also includes:
- Background scheduler for periodic user sync
- VoteBot proxy endpoints for chat and WebSocket streaming
"""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import routers
from app.routes import voatz_router, brevo_router, sync_router, votebot_router, webflow_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events.

    Startup: Start the background scheduler
    Shutdown: Stop the background scheduler
    """
    # Startup
    try:
        from scheduler import start_scheduler

        start_scheduler()
        logger.info("Background scheduler started")
    except Exception as e:
        logger.warning(f"Could not start scheduler (config may be missing): {e}")

    yield

    # Shutdown
    try:
        from scheduler import stop_scheduler

        stop_scheduler()
        logger.info("Background scheduler stopped")
    except Exception as e:
        logger.warning(f"Error stopping scheduler: {e}")


app = FastAPI(
    title="DDP-API",
    description="Digital Democracy Project API - Voatz/Brevo middleware and VoteBot proxy",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(voatz_router)
app.include_router(brevo_router)
app.include_router(sync_router)
app.include_router(votebot_router)
app.include_router(webflow_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "DDP-API", "version": "2.0.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True)
