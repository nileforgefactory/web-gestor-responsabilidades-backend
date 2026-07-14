"""proyectos_matriz_sgr.municipio: VARCHAR(300) -> TEXT

Revision ID: sgr010
Revises: sgr009
Create Date: 2026-07-14

Proyectos que abarcan muchos municipios (listas separadas por coma en el
Excel GESPROY/DNP) superaban el límite de VARCHAR(300), haciendo fallar
el backfill/carga con "Data too long for column 'municipio'". MySQL no
permite indexar una columna TEXT sin longitud de prefijo, así que se
elimina el índice existente antes de ampliar el tipo.
"""

from alembic import op
import sqlalchemy as sa

revision = "sgr010"
down_revision = "sgr009"
branch_labels = None
depends_on = None


def _index_exists(connection: sa.Connection, table: str, index_name: str) -> bool:
    idxs = {i["name"] for i in sa.inspect(connection).get_indexes(table)}
    return index_name in idxs


def upgrade() -> None:
    connection = op.get_bind()
    if _index_exists(connection, "proyectos_matriz_sgr", "ix_proyectos_matriz_sgr_municipio"):
        op.drop_index("ix_proyectos_matriz_sgr_municipio", table_name="proyectos_matriz_sgr")
    op.alter_column(
        "proyectos_matriz_sgr",
        "municipio",
        existing_type=sa.String(length=300),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "proyectos_matriz_sgr",
        "municipio",
        existing_type=sa.Text(),
        type_=sa.String(length=300),
        existing_nullable=True,
    )
    op.create_index("ix_proyectos_matriz_sgr_municipio", "proyectos_matriz_sgr", ["municipio"])
