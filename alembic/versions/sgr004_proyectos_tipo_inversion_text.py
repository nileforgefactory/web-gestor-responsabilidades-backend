"""proyectos_sgr.tipo_inversion: VARCHAR(120) -> TEXT

Revision ID: sgr004
Revises: sgr003
Create Date: 2026-07-05

El agente de duplicidad a veces asigna a tipo_inversion el mismo texto
largo del campo nombre (Text), lo que superaba el límite de
VARCHAR(120) y hacía fallar el INSERT ("Data too long for column
'tipo_inversion'").
"""

from alembic import op
import sqlalchemy as sa

revision = "sgr004"
down_revision = "sgr003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "proyectos_sgr",
        "tipo_inversion",
        existing_type=sa.String(length=120),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "proyectos_sgr",
        "tipo_inversion",
        existing_type=sa.Text(),
        type_=sa.String(length=120),
        existing_nullable=True,
    )
