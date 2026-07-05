"""roles, usuarios y superadmin bootstrap

Revision ID: a1b2c3d4e5f6
Revises: 740b43697f28
Create Date: 2026-06-04

Las tablas ``roles`` y ``usuarios`` las crea ``0001_initial_schema`` (create_all).
Esta revisión solo inserta el catálogo de roles y el usuario superadmin.
"""
from __future__ import annotations

import json
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.slices.auth.security import hash_password

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "740b43697f28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_USUARIO_ID = "00000000-0000-4000-8000-000000000001"
ROLE_ADMINISTRADOR_ID = "00000000-0000-4000-8000-000000000002"
ROLE_SUPERADMIN_ID = "00000000-0000-4000-8000-000000000003"
SUPERADMIN_USER_ID = "00000000-0000-4000-8000-000000000100"

_ROLES_SEED = [
    {
        "id": ROLE_USUARIO_ID,
        "codigo": "usuario",
        "nombre": "Usuario",
        "descripcion": "Solo lectura en su territorio.",
    },
    {
        "id": ROLE_ADMINISTRADOR_ID,
        "codigo": "administrador",
        "nombre": "Administrador",
        "descripcion": "Gestión completa dentro de su territorio.",
    },
    {
        "id": ROLE_SUPERADMIN_ID,
        "codigo": "superadmin",
        "nombre": "Super Administrador",
        "descripcion": "Provisionamiento global de usuarios y territorios.",
    },
]


def _normalize_territorio(raw: str) -> list:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return ["COLOMBIA", None, None]


def _collection_id(territorio: list) -> str:
    parts: list[str] = []
    for segment in territorio:
        if not segment:
            continue
        parts.append(
            "_".join(token for token in str(segment).upper().split() if token)
        )
    return "_".join(parts) if parts else "COLOMBIA"


def _table_exists(connection: sa.Connection, name: str) -> bool:
    return name in sa.inspect(connection).get_table_names()


def upgrade() -> None:
    connection = op.get_bind()

    if not _table_exists(connection, "roles") or not _table_exists(connection, "usuarios"):
        raise RuntimeError(
            "Faltan tablas roles/usuarios. Ejecute primero la revisión 0001_initial_schema."
        )

    roles_table = sa.table(
        "roles",
        sa.column("id", sa.String),
        sa.column("codigo", sa.String),
        sa.column("nombre", sa.String),
        sa.column("descripcion", sa.Text),
    )
    for row in _ROLES_SEED:
        exists = connection.execute(
            sa.text("SELECT 1 FROM roles WHERE codigo = :codigo LIMIT 1"),
            {"codigo": row["codigo"]},
        ).fetchone()
        if not exists:
            op.bulk_insert(roles_table, [row])

    email = os.getenv("AUTH_BOOTSTRAP_ADMIN_EMAIL", "superadmin@gestor.local").strip().lower()
    password = os.getenv("AUTH_BOOTSTRAP_ADMIN_PASSWORD", "SuperAdmin123!")
    nombre = os.getenv("AUTH_BOOTSTRAP_ADMIN_NOMBRE", "Super Administrador")
    territorio = _normalize_territorio(
        os.getenv("AUTH_BOOTSTRAP_ADMIN_TERRITORIO", '["COLOMBIA", null, null]')
    )
    territorio_json = json.dumps(territorio, ensure_ascii=False)
    coleccion_id = _collection_id(territorio)

    superadmin_exists = connection.execute(
        sa.text(
            "SELECT 1 FROM usuarios WHERE id = :id OR email = :email LIMIT 1"
        ),
        {"id": SUPERADMIN_USER_ID, "email": email},
    ).fetchone()

    if not superadmin_exists:
        usuarios_table = sa.table(
            "usuarios",
            sa.column("id", sa.String),
            sa.column("nombre", sa.String),
            sa.column("email", sa.String),
            sa.column("password_hash", sa.String),
            sa.column("rol_id", sa.String),
            sa.column("territorio", sa.Text),
            sa.column("coleccion_id", sa.String),
            sa.column("activo", sa.Boolean),
            sa.column("estado_onboarding", sa.String),
            sa.column("password_provisional", sa.Boolean),
        )
        op.bulk_insert(
            usuarios_table,
            [
                {
                    "id": SUPERADMIN_USER_ID,
                    "nombre": nombre,
                    "email": email,
                    "password_hash": hash_password(password),
                    "rol_id": ROLE_SUPERADMIN_ID,
                    "territorio": territorio_json,
                    "coleccion_id": coleccion_id,
                    "activo": True,
                    # El superadmin de bootstrap ya tiene contraseña definitiva
                    # (viene de env var), no debe quedar atrapado en el flujo
                    # de onboarding SGR de usuarios nuevos.
                    "estado_onboarding": "plan_analizado",
                    "password_provisional": False,
                }
            ],
        )


def downgrade() -> None:
    """Elimina solo datos insertados por esta revisión (no borra tablas)."""
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM usuarios WHERE id = :id"),
        {"id": SUPERADMIN_USER_ID},
    )
    for role_id in (ROLE_SUPERADMIN_ID, ROLE_ADMINISTRADOR_ID, ROLE_USUARIO_ID):
        connection.execute(
            sa.text(
                "DELETE FROM roles WHERE id = :id "
                "AND NOT EXISTS (SELECT 1 FROM usuarios u WHERE u.rol_id = :id)"
            ),
            {"id": role_id},
        )
