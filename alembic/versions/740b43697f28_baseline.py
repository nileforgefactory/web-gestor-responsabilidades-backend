"""baseline — defaults de timestamps en tablas existentes

Revision ID: 740b43697f28
Revises: 0001_initial_schema
Create Date: 2026-05-24 17:25:33.835780

Ajusta ``server_default`` de columnas ``creado_en`` / ``actualizado_en``
en planes, base_conocimiento y alertas_normativas.

Downgrade: revierte a ``(now())`` (estado previo a esta revisión).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "740b43697f28"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "alertas_normativas",
        "creado_en",
        existing_type=mysql.DATETIME(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "base_conocimiento",
        "creado_en",
        existing_type=mysql.DATETIME(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "planes",
        "creado_en",
        existing_type=mysql.DATETIME(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "planes",
        "actualizado_en",
        existing_type=mysql.DATETIME(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "planes",
        "actualizado_en",
        existing_type=mysql.DATETIME(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "planes",
        "creado_en",
        existing_type=mysql.DATETIME(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "base_conocimiento",
        "creado_en",
        existing_type=mysql.DATETIME(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "alertas_normativas",
        "creado_en",
        existing_type=mysql.DATETIME(),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
