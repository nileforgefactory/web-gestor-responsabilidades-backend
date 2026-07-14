"""proyectos_matriz_sgr: catalogo MySQL de proyectos GESPROY/DNP indexados

Revision ID: sgr009
Revises: sgr008
Create Date: 2026-07-14

Hasta ahora los proyectos cargados desde el Excel GESPROY/DNP solo se
indexaban en Qdrant (sin forma de listarlos/paginarlos). Esta tabla es un
catalogo liviano en MySQL, poblado en cada carga exitosa del Excel, para
que el frontend pueda mostrar una tabla paginable/buscable (igual que la
Base de Conocimiento).
"""
from alembic import op
import sqlalchemy as sa

revision = "sgr009"
down_revision = "sgr008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proyectos_matriz_sgr",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bpin", sa.String(length=50), nullable=True),
        sa.Column("nombre", sa.String(length=500), nullable=False),
        sa.Column("municipio", sa.String(length=300), nullable=True),
        sa.Column("departamento", sa.String(length=150), nullable=True),
        sa.Column("sector", sa.String(length=150), nullable=True),
        sa.Column("estado", sa.String(length=100), nullable=True),
        sa.Column("valor_sgr", sa.String(length=100), nullable=True),
        sa.Column("fecha_aprobacion", sa.String(length=50), nullable=True),
        sa.Column("qdrant_doc_id", sa.String(length=200), nullable=True),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_proyectos_matriz_sgr_bpin", "proyectos_matriz_sgr", ["bpin"])
    op.create_index("ix_proyectos_matriz_sgr_nombre", "proyectos_matriz_sgr", ["nombre"])
    op.create_index("ix_proyectos_matriz_sgr_municipio", "proyectos_matriz_sgr", ["municipio"])
    op.create_index("ix_proyectos_matriz_sgr_departamento", "proyectos_matriz_sgr", ["departamento"])


def downgrade() -> None:
    op.drop_table("proyectos_matriz_sgr")
