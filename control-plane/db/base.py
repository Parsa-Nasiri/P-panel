"""Verdent Platform — async engine & session factory (SQLAlchemy 2.0)."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from domain.config import settings

engine = create_async_engine(
    settings.async_database_url,
    echo=(settings.environment == "development"),
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency."""
    async with SessionLocal() as session:
        yield session
