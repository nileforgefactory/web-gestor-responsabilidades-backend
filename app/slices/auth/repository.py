"""Acceso a datos de roles y usuarios."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.slices.auth.models import Role, User
from app.slices.common.territorio import (
    collection_id_from_territorio,
    normalize_territorio,
    territorio_to_json,
)

_ASSIGNABLE_ROLES = frozenset({"usuario", "administrador"})


def _territorio_fields(territorio_raw: list[str | None] | str) -> tuple[str, str]:
    territorio = normalize_territorio(territorio_raw)
    return territorio_to_json(territorio), collection_id_from_territorio(territorio)


async def get_role_by_codigo(db: AsyncSession, codigo: str) -> Role | None:
    stmt = select(Role).where(Role.codigo == codigo.strip().lower())
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_roles(db: AsyncSession) -> list[Role]:
    stmt = select(Role).order_by(Role.codigo)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_users(db: AsyncSession) -> int:
    result = await db.execute(select(User.id))
    return len(result.scalars().all())


def _user_stmt():
    return select(User).options(joinedload(User.role))


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = _user_stmt().where(User.email == email.strip().lower())
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_id(db: AsyncSession, user_id: str) -> User | None:
    stmt = _user_stmt().where(User.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_territory(
    db: AsyncSession,
    *,
    coleccion_id: str,
    include_inactive: bool = False,
) -> list[User]:
    stmt = _user_stmt().where(User.coleccion_id == coleccion_id)
    if not include_inactive:
        stmt = stmt.where(User.activo.is_(True))
    stmt = stmt.order_by(User.creado_en.desc())
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


async def list_all_active(
    db: AsyncSession,
    *,
    coleccion_id: str | None = None,
) -> list[User]:
    stmt = _user_stmt().where(User.activo.is_(True))
    if coleccion_id:
        stmt = stmt.where(User.coleccion_id == coleccion_id.strip().upper())
    stmt = stmt.order_by(User.coleccion_id, User.creado_en.desc())
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


async def create_user(
    db: AsyncSession,
    *,
    nombre: str,
    email: str,
    password_hash: str,
    rol_codigo: str,
    territorio_raw: list[str | None] | str,
) -> User:
    codigo = rol_codigo.strip().lower()
    if codigo not in _ASSIGNABLE_ROLES:
        raise ValueError(f"Rol no asignable vía API: {rol_codigo!r}")

    role = await get_role_by_codigo(db, codigo)
    if role is None:
        raise ValueError(f"Rol no encontrado: {rol_codigo!r}")

    territorio_json, coleccion_id = _territorio_fields(territorio_raw)
    user = User(
        nombre=nombre.strip(),
        email=email.strip().lower(),
        password_hash=password_hash,
        rol_id=role.id,
        territorio=territorio_json,
        coleccion_id=coleccion_id,
        activo=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, attribute_names=["role"])
    return user


async def update_rol(db: AsyncSession, user: User, rol_codigo: str) -> User:
    codigo = rol_codigo.strip().lower()
    if codigo not in _ASSIGNABLE_ROLES:
        raise ValueError(f"Rol no asignable vía API: {rol_codigo!r}")

    role = await get_role_by_codigo(db, codigo)
    if role is None:
        raise ValueError(f"Rol no encontrado: {rol_codigo!r}")

    user.rol_id = role.id
    await db.flush()
    await db.refresh(user, attribute_names=["role"])
    return user


async def soft_delete(db: AsyncSession, user: User) -> User:
    user.activo = False
    user.eliminado_en = datetime.now(UTC).replace(tzinfo=None)
    await db.flush()
    await db.refresh(user, attribute_names=["role"])
    return user
