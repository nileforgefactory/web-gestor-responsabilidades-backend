"""fichas_mga: agregar checklist_verificacion (evaluacion IA del checklist final)

Revision ID: sgr008
Revises: sgr007
Create Date: 2026-07-14

Persiste, por cada Ficha MGA, si cada ítem evaluable del checklist final de
verificación (20 de 22, excluye soportes físicos y revisión por un par) quedó
cumplido o no, según el texto generado por la IA, con motivo breve.
"""
from alembic import op
import sqlalchemy as sa

revision = "sgr008"
down_revision = "sgr007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fichas_mga",
        sa.Column("checklist_verificacion", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fichas_mga", "checklist_verificacion")
