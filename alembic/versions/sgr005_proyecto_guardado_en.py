"""proyectos_sgr: agregar guardado_en (guardado explicito del usuario)

Revision ID: sgr005
Revises: sgr004
Create Date: 2026-07-12

Antes, evaluar_plan_sgr borraba y recreaba TODOS los proyectos "descubrimiento"
de un plan en cada llamada (con UUIDs nuevos), lo que invalidaba silenciosamente
cualquier ficha MGA/link ya generado (bug de descarga 404). guardado_en permite
distinguir un borrador de sesion (NULL) de un proyecto que el usuario confirmo
explicitamente guardar (timestamp), y proteger a estos ultimos del barrido de
re-evaluacion.
"""

from alembic import op
import sqlalchemy as sa

revision = "sgr005"
down_revision = "sgr004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proyectos_sgr",
        sa.Column("guardado_en", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proyectos_sgr", "guardado_en")
