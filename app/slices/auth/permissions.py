"""Reglas de acceso por rol y territorio."""

from __future__ import annotations

from fastapi import HTTPException

from app.slices.auth.models import User
from app.slices.common.territorio import (
    allowed_collection_ids,
    collection_id_from_territorio,
    is_collection_allowed,
    normalize_territorio,
)


def rol_codigo(user: User) -> str:
    return user.rol_codigo


def is_superadmin(user: User) -> bool:
    return rol_codigo(user) == "superadmin"


def is_admin(user: User) -> bool:
    return rol_codigo(user) in ("administrador", "superadmin")


def can_write(user: User) -> bool:
    return is_admin(user)


def user_territorio(user: User) -> list[str | None]:
    from app.slices.common.territorio import territorio_from_json

    return territorio_from_json(user.territorio) or ["COLOMBIA", None, None]


def allowed_collections_for_user(user: User) -> frozenset[str]:
    if is_superadmin(user):
        return frozenset()
    return allowed_collection_ids(user_territorio(user))


def resolve_territorio_for_creation(
    actor: User,
    territorio_raw: list[str | None] | None,
) -> list[str | None]:
    """
    Territorio efectivo al crear un usuario.

    - Sin ``territorio`` → territorio del admin que crea.
    - Superadmin → cualquier territorio válido.
    - Admin territorial → solo su territorio.
    """
    actor_territorio = normalize_territorio(user_territorio(actor))

    if territorio_raw is None:
        return actor_territorio

    requested = normalize_territorio(territorio_raw)
    if is_superadmin(actor):
        return requested

    if collection_id_from_territorio(requested) != actor.coleccion_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Solo el superadmin puede crear usuarios en otro territorio. "
                f"Su territorio es {actor.coleccion_id!r}."
            ),
        )
    return requested


def ensure_can_manage_user(actor: User, target: User) -> None:
    if is_superadmin(actor):
        return
    if actor.coleccion_id != target.coleccion_id:
        raise HTTPException(
            status_code=403,
            detail="No puede gestionar usuarios de otro territorio.",
        )


def ensure_collection_access(user: User, collection_id: str) -> None:
    if is_superadmin(user):
        return
    if not is_collection_allowed(user_territorio(user), collection_id):
        raise HTTPException(
            status_code=403,
            detail=f"No tiene acceso a la colección '{collection_id}'.",
        )


def ensure_collections_access(user: User, collection_ids: list[str]) -> None:
    if is_superadmin(user):
        return
    allowed = allowed_collection_ids(user_territorio(user))
    forbidden = {cid.strip().upper() for cid in collection_ids} - allowed
    if forbidden:
        raise HTTPException(
            status_code=403,
            detail=(
                "No tiene acceso a las colecciones: "
                + ", ".join(sorted(forbidden))
            ),
        )


def filter_allowed_collections(user: User, collection_ids: list[str]) -> list[str]:
    if is_superadmin(user):
        return collection_ids
    allowed = allowed_collection_ids(user_territorio(user))
    return [cid for cid in collection_ids if cid.strip().upper() in allowed]
