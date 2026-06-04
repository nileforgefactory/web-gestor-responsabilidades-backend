"""Esquema inicial desde modelos SQLAlchemy."""

from __future__ import annotations

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


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
