"""fichas_mga: agregar cobertura_preguntas (instrumento MGA de 50 preguntas)

Revision ID: sgr007
Revises: sgr006
Create Date: 2026-07-14

Persiste, por cada Ficha MGA, qué preguntas del instrumento (DNP, Instrumento
de formulación MGA para municipios Cat. 5/6) quedaron respondidas, parciales o
sin responder — para mostrar alertas de cobertura al usuario tras generar la
ficha con IA.
"""

from alembic import op
import sqlalchemy as sa

revision = "sgr007"
down_revision = "sgr006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fichas_mga",
        sa.Column("cobertura_preguntas", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fichas_mga", "cobertura_preguntas")
