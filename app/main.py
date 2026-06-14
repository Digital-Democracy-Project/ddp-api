"""
DDP-API FastAPI Application.

Auth gateway and API proxy for the Digital Democracy Project.
Routes requests to internal services (VoteBot, DDP-Sync) and external APIs
(Voatz, Brevo, Webflow CMS).

Scheduling and data pipelines are handled by DDP-Sync (port 8001).
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
from app.routes import voatz_router, brevo_router, votebot_router, webflow_router
from app.routes.ddp_sync_proxy import router as ddp_sync_router
from app.routes.openstates_proxy import router as openstates_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan. DDP-API is stateless — no background jobs."""
    logger.info("DDP-API started (proxy mode)")
    yield
    logger.info("DDP-API shutdown")


app = FastAPI(
    title="DDP-API",
    description="Digital Democracy Project API - Auth gateway and service proxy",
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
app.include_router(votebot_router)
app.include_router(webflow_router)

# Catch-all proxy for ddp-sync — register under /votebot prefix
# so external paths don't change (e.g., /votebot/sync/unified → ddp-sync)
app.include_router(ddp_sync_router, prefix="/votebot")

# Also register trigger routes at root level (for /trigger/* paths)
app.include_router(ddp_sync_router)

# Local OpenStates api-v3 proxy — routes /openstates/* to Mac Studio :8002 via WireGuard
app.include_router(openstates_router)


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
