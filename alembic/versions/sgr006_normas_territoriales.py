"""normas_territoriales: catalogo ampliable del indexer (normas propias del territorio)

Revision ID: sgr006
Revises: sgr005
Create Date: 2026-07-12

Permite al admin registrar normas propias del municipio/departamento (acuerdos,
ordenanzas, decretos locales) que el indexer suma a las ~36 nacionales de
normas_base.py, para que el catalogo no quede fijo.
"""

from alembic import op
import sqlalchemy as sa

revision = "sgr006"
down_revision = "sgr005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "normas_territoriales",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("codigo", sa.String(length=200), nullable=False),
        sa.Column("territorio", sa.String(length=200), nullable=True),
        sa.Column("prioridad", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_normas_territoriales_activo", "normas_territoriales", ["activo"])


def downgrade() -> None:
    op.drop_index("ix_normas_territoriales_activo", table_name="normas_territoriales")
    op.drop_table("normas_territoriales")
