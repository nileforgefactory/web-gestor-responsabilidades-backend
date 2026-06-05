"""Esquema inicial desde modelos SQLAlchemy.

Revision ID: 0001_initial_schema
Revises: (ninguna — raíz)
Create Date: 2026-05-24

Crea todas las tablas registradas en ``app.db.models_registry`` vía ``create_all``.
Incluye: planes, base_conocimiento, alertas_normativas, roles, usuarios, etc.

Downgrade: elimina todas las tablas (``drop_all``).
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import app.db.models_registry  # noqa: F401
    from alembic import op

    from app.core.database import Base

    connection = op.get_bind()
    Base.metadata.create_all(bind=connection)


def downgrade() -> None:
    import app.db.models_registry  # noqa: F401
    from alembic import op

    from app.core.database import Base

    connection = op.get_bind()
    Base.metadata.drop_all(bind=connection)
