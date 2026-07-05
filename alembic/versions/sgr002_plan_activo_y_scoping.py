"""Plan activo por usuario + scoping de planes por territorio

Revision ID: sgr002
Revises: sgr001
Create Date: 2026-07-03

Agrega:
- planes.coleccion_id — territorio dueño del plan (mismo valor que usuarios.coleccion_id),
  usado para filtrar la lista de planes visibles por usuario.
- usuarios.plan_activo_id — plan actualmente seleccionado como contexto de trabajo
  para los flujos SGR (Modo 2 y cualquier operación sin plan_id explícito).

Ambas columnas son nullable: los planes existentes quedan sin colección asignada
(visibles solo para superadmin hasta que se les asigne una) y los usuarios existentes
sin plan activo (se resuelve en runtime al último plan `analizado` de su colección).
"""

from alembic import op
import sqlalchemy as sa

revision = "sgr002"
down_revision = "sgr001"
branch_labels = None
depends_on = None


def _column_exists(connection: sa.Connection, table: str, column: str) -> bool:
    cols = {c["name"] for c in sa.inspect(connection).get_columns(table)}
    return column in cols


def _index_exists(connection: sa.Connection, table: str, index_name: str) -> bool:
    idxs = {i["name"] for i in sa.inspect(connection).get_indexes(table)}
    return index_name in idxs


def _fk_exists(connection: sa.Connection, table: str, fk_name: str) -> bool:
    fks = {fk["name"] for fk in sa.inspect(connection).get_foreign_keys(table)}
    return fk_name in fks


def upgrade() -> None:
    # Idempotente: en bases nuevas, 0001_initial_schema (create_all desde el
    # estado actual de los modelos) ya crea estas columnas.
    connection = op.get_bind()

    if not _column_exists(connection, "planes", "coleccion_id"):
        op.add_column(
            "planes",
            sa.Column("coleccion_id", sa.String(length=100), nullable=True,
                       comment="Territorio dueño del plan (igual a usuarios.coleccion_id)"),
        )
    if not _index_exists(connection, "planes", "idx_planes_coleccion"):
        op.create_index("idx_planes_coleccion", "planes", ["coleccion_id"])

    if not _column_exists(connection, "usuarios", "plan_activo_id"):
        op.add_column(
            "usuarios",
            sa.Column("plan_activo_id", sa.String(length=36), nullable=True,
                       comment="Plan seleccionado como contexto activo para flujos SGR"),
        )
    if not _fk_exists(connection, "usuarios", "fk_usuarios_plan_activo"):
        op.create_foreign_key(
            "fk_usuarios_plan_activo",
            "usuarios", "planes",
            ["plan_activo_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    op.drop_constraint("fk_usuarios_plan_activo", "usuarios", type_="foreignkey")
    op.drop_column("usuarios", "plan_activo_id")

    op.drop_index("idx_planes_coleccion", table_name="planes")
    op.drop_column("planes", "coleccion_id")
