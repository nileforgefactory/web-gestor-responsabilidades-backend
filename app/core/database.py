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
from contextlib import asynccontextmanager

import logging

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


logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(
    db_url: str,
    *,
    pool_pre_ping: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> None:
    """Inicializa el engine y la fábrica de sesiones. Llamar una sola vez al arrancar."""
    global _engine, _session_factory
    if _engine is not None:
        return
    _engine = create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=pool_pre_ping,
        pool_recycle=3600,
        pool_size=max(5, pool_size),
        max_overflow=max_overflow,
    )
    logger.info("MySQL async engine listo (pool_pre_ping=%s)", pool_pre_ping)
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


def mysql_available() -> bool:
    """True si MYSQL_URL fue configurado y el pool de sesiones está activo."""
    return _session_factory is not None


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """
    Sesión independiente con commit/rollback (segura para tareas en paralelo).

    Raises:
        RuntimeError: si MySQL no está inicializado.
    """
    if _session_factory is None:
        raise RuntimeError("MySQL no configurado")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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
