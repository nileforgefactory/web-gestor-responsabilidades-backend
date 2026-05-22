"""Modelo SQLAlchemy para alertas normativas."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AlertaNormativa(Base):
    __tablename__ = "alertas_normativas"

    id:          Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id:     Mapped[str | None] = mapped_column(String(36), ForeignKey("planes.id", ondelete="CASCADE"), index=True)
    tipo:        Mapped[str]       = mapped_column(
        Enum("modificacion", "derogacion", "nueva_norma", "jurisprudencia"),
        default="modificacion",
    )
    titulo:      Mapped[str]       = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    norma_ref:   Mapped[str | None] = mapped_column(String(100))  # código de la norma afectada
    severidad:   Mapped[str]       = mapped_column(Enum("alta", "media", "baja"), default="media")
    leida:       Mapped[bool]      = mapped_column(Boolean, default=False)
    creado_en:   Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
