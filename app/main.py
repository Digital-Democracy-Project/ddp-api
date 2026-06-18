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
from fastapi import Depends, FastAPI
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
from app.middleware.auth import admin_auth
from app.routes import voatz_router, brevo_router, votebot_router, webflow_router
from app.routes.admin import router as admin_router
from app.routes.ddp_sync_proxy import router as ddp_sync_router
from app.routes.openstates_proxy import router as openstates_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: warm key store on startup, flush last_used_at on shutdown."""
    from app.services.key_store import get_key_store
    get_key_store().reload()
    logger.info("DDP-API started (proxy mode)")
    yield
    # Flush in-memory last_used_at back to Secrets Manager before exit.
    # best-effort only — SIGKILL/OOM drops this step.
    get_key_store().flush_last_used()
    logger.info("DDP-API shutdown")


app = FastAPI(
    title="DDP-API",
    description="Digital Democracy Project API — auth gateway and service proxy",
    version="2.0.0",
    lifespan=lifespan,
    # Docs are served via custom routes below so we can split public vs admin schemas
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(voatz_router)
app.include_router(brevo_router)
app.include_router(votebot_router)
app.include_router(webflow_router)
app.include_router(admin_router)

# Catch-all proxy for ddp-sync
app.include_router(ddp_sync_router, prefix="/votebot")
app.include_router(ddp_sync_router)

# Local OpenStates api-v3 proxy
app.include_router(openstates_router)


# ---------------------------------------------------------------------------
# Public docs — excludes /admin routes; safe to expose in a self-service portal
# ---------------------------------------------------------------------------

@app.get("/openapi.json", include_in_schema=False)
async def public_openapi():
    from fastapi.openapi.utils import get_openapi
    return get_openapi(
        title="DDP-API",
        version="2.0.0",
        description="Digital Democracy Project API — auth gateway and service proxy",
        routes=[r for r in app.routes if not getattr(r, "path", "").startswith("/admin")],
    )


@app.get("/docs", include_in_schema=False)
async def public_docs():
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(openapi_url="/openapi.json", title="DDP-API")


@app.get("/redoc", include_in_schema=False)
async def public_redoc():
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(openapi_url="/openapi.json", title="DDP-API")


# ---------------------------------------------------------------------------
# Admin docs — admin_auth required; shows only /admin routes
# ---------------------------------------------------------------------------

@app.get("/admin/openapi.json", include_in_schema=False)
async def admin_openapi(_key=Depends(admin_auth)):
    from fastapi.openapi.utils import get_openapi
    return get_openapi(
        title="DDP-API Admin",
        version="2.0.0",
        description="DDP-API admin endpoints — key management",
        routes=[r for r in app.routes if getattr(r, "path", "").startswith("/admin")],
    )


@app.get("/admin/docs", include_in_schema=False)
async def admin_docs(_key=Depends(admin_auth)):
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(openapi_url="/admin/openapi.json", title="DDP-API Admin")


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """Service info."""
    return {"status": "ok", "service": "DDP-API", "version": "2.0.0"}


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True)
