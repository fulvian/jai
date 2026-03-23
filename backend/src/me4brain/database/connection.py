"""
Database connection module - Async SQLAlchemy setup.

Provides async database connections using SQLAlchemy 2.0
with connection pooling for production use.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from me4brain.config.settings import get_settings

# Base class for all models
Base = declarative_base()

# Global engine and session factory
_engine = None
_session_factory = None


def get_database_url() -> str:
    """Get the async database URL from settings."""
    settings = get_settings()
    # Default to SQLite for development if no PostgreSQL URL
    default_url = "sqlite+aiosqlite:///./me4brain.db"
    return getattr(settings, "database_url", None) or default_url


def get_engine():
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        database_url = get_database_url()
        # For SQLite, don't use connection pool
        if "sqlite" in database_url:
            _engine = create_async_engine(
                database_url,
                echo=False,
                poolclass=NullPool,
            )
        else:
            _engine = create_async_engine(
                database_url,
                echo=False,
                pool_size=20,
                max_overflow=40,
                pool_recycle=3600,
                pool_pre_ping=True,
            )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get a database session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for getting a database session outside of FastAPI."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database tables."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
