import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.database import init_redis_pool, close_redis_pool, engine
from app.api.v1.health import router as health_router
from app.api.v1.webhooks import router as webhooks_router
from app.gateway.webhooks import router as external_webhooks_router
from app.gateway.call_bridge import router as call_bridge_router
from app.gateway.music_api import router as music_router

# Configure Logger
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nexusai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager handling startup and shutdown hooks."""
    logger.info(f"Initializing {settings.APP_NAME} in [{settings.APP_ENV}] mode...")
    
    # Initialize Redis pool
    try:
        await init_redis_pool()
        logger.info("Connected to Redis connection pool.")
    except Exception as exc:
        logger.error(f"Redis initialization warning (will retry on demand): {exc}")

    yield

    # Clean shutdown
    logger.info("Shutting down NEXUS AI...")
    await close_redis_pool()
    await engine.dispose()
    logger.info("Database and Redis connections gracefully terminated.")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Autonomous Multi-Agent Automation Engine with LangGraph, PostgreSQL/pgvector, and Redis.",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled system error on path '{request.url.path}': {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unhandled error occurred while processing the request.",
            "path": request.url.path,
        },
    )


# Attach Core Routers
app.include_router(health_router)
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(external_webhooks_router, prefix="/api/v1")
app.include_router(call_bridge_router, prefix="/api/v1")
app.include_router(music_router, prefix="/api/v1")

# Mount Static Files for WebRTC / Call Dashboard
from fastapi.staticfiles import StaticFiles
from pathlib import Path
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "status": "operational",
        "docs_url": "/docs",
    }

