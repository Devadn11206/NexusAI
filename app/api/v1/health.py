from datetime import datetime, timezone
from fastapi import APIRouter
from app.core.database import check_postgres_connection, check_redis_connection
from app.api.v1.schemas import HealthStatusResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthStatusResponse)
async def health_check() -> HealthStatusResponse:
    """Telemetry endpoint querying live PostgreSQL and Redis connections."""
    postgres_ok = await check_postgres_connection()
    redis_ok = await check_redis_connection()

    all_healthy = postgres_ok and redis_ok
    status_str = "healthy" if all_healthy else "degraded"

    return HealthStatusResponse(
        status=status_str,
        postgres="connected" if postgres_ok else "disconnected",
        redis="connected" if redis_ok else "disconnected",
        timestamp=datetime.now(timezone.utc),
    )

