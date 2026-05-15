"""Motor asíncrono SQLAlchemy + fábrica de sesiones.

Uso:
    from app.core.database import Base, init_db, create_tables, get_db

    # al arrancar la app:
    init_db(settings.mysql_url)
    await create_tables()

    # en un endpoint (via Depends):
    async def mi_endpoint(db: AsyncSession = Depends(get_db)): ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(db_url: str) -> None:
    """Inicializa el engine y la fábrica de sesiones. Llamar una sola vez al arrancar."""
    global _engine, _session_factory
    if _engine is not None:
        return
    _engine = create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=5,
        max_overflow=10,
    )
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def create_tables() -> None:
    """Crea todas las tablas registradas en Base.metadata si no existen."""
    if _engine is None:
        return
    # Los modelos deben estar importados antes de llamar a esta función
    # para que sus tablas estén registradas en Base.metadata.
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()


async def get_optional_db() -> AsyncGenerator[AsyncSession | None, None]:
    """
    Sesión MySQL opcional para endpoints que pueden omitir persistencia.

    Yields:
        AsyncSession si MYSQL_URL está configurado; None en caso contrario.
    """
    if _session_factory is None:
        yield None
        return
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI que entrega una sesión con commit/rollback automático."""
    if _session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="Base de datos MySQL no configurada. Establece MYSQL_URL en las variables de entorno.",
        )
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
