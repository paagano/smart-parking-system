from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# ==========================================================
# Database Engine
# ==========================================================

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# ==========================================================
# Session Factory
# ==========================================================

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)

# ==========================================================
# Database Dependency
# ==========================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an asynchronous
    SQLAlchemy database session.

    Yields:
        AsyncSession: Active database session.
    """

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()