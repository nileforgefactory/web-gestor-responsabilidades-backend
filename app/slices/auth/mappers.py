"""Utilidades para mapear usuarios a respuestas API."""

from __future__ import annotations

from app.slices.auth.models import User
from app.slices.auth.schemas import MeResponse, RolCodigo, TerritorioOut, UserSummary
from app.slices.common.territorio import (
    collection_id_from_territorio,
    territorio_from_json,
)


def _territorio_out(user: User) -> TerritorioOut:
    territorio = territorio_from_json(user.territorio) or ["COLOMBIA", None, None]
    return TerritorioOut(
        pais=territorio[0] or "COLOMBIA",
        departamento=territorio[1],
        municipio=territorio[2],
        coleccion_id=user.coleccion_id or collection_id_from_territorio(territorio),
    )


def _rol_out(user: User) -> RolCodigo:
    return user.rol_codigo  # type: ignore[return-value]


def to_me_response(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        nombre=user.nombre,
        email=user.email,
        rol=_rol_out(user),
        territorio=_territorio_out(user),
        activo=user.activo,
        creado_en=user.creado_en,
        plan_activo_id=user.plan_activo_id,
    )


def to_user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        nombre=user.nombre,
        email=user.email,
        rol=_rol_out(user),
        territorio=_territorio_out(user),
        activo=user.activo,
        creado_en=user.creado_en,
    )
