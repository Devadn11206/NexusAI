import logging
from typing import AsyncGenerator, Optional
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text
from app.config import settings

logger = logging.getLogger(__name__)

# Async SQLAlchemy Engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Async Redis Connection Pool
redis_pool: Optional[aioredis.ConnectionPool] = None
redis_client: Optional[aioredis.Redis] = None


async def init_redis_pool() -> aioredis.Redis:
    """Initialize Redis connection pool."""
    global redis_pool, redis_client
    if redis_client is None:
        redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
            decode_responses=True,
        )
        redis_client = aioredis.Redis(connection_pool=redis_pool)
        logger.info("Redis connection pool initialized.")
    return redis_client


async def close_redis_pool() -> None:
    """Close Redis connection pool."""
    global redis_client, redis_pool
    if redis_client:
        await redis_client.aclose()
        logger.info("Redis connection closed.")
        redis_client = None
    if redis_pool:
        await redis_pool.disconnect()
        redis_pool = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_postgres_connection() -> bool:
    """Probe PostgreSQL database health."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"PostgreSQL health check failed: {exc}")
        return False


async def check_redis_connection() -> bool:
    """Probe Redis database health."""
    try:
        client = redis_client
        if client is None:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            res = await client.ping()
            await client.aclose()
            return bool(res)
        return bool(await client.ping())
    except Exception as exc:
        logger.warning(f"Redis health check failed: {exc}")
        return False

