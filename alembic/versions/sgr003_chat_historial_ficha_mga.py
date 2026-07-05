"""Historial de chat para edición conversacional de la Ficha MGA

Revision ID: sgr003
Revises: sgr002
Create Date: 2026-07-03

Agrega fichas_mga.chat_historial (JSON) para persistir la conversación de
edición asistida por IA sobre el documento MGA (turnos usuario/asistente).
"""

from alembic import op
import sqlalchemy as sa

revision = "sgr003"
down_revision = "sgr002"
branch_labels = None
depends_on = None


def _column_exists(connection: sa.Connection, table: str, column: str) -> bool:
    cols = {c["name"] for c in sa.inspect(connection).get_columns(table)}
    return column in cols


def upgrade() -> None:
    connection = op.get_bind()
    if not _column_exists(connection, "fichas_mga", "chat_historial"):
        op.add_column(
            "fichas_mga",
            sa.Column("chat_historial", sa.JSON(), nullable=True,
                       comment="Historial de chat de edición: lista de {role, texto, timestamp}"),
        )


def downgrade() -> None:
    op.drop_column("fichas_mga", "chat_historial")
