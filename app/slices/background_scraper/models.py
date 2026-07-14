"""Modelo SQLAlchemy para normas territoriales del indexer.

Además de las ~36 normas nacionales de `normas_base.py` (semilla fija), el admin
puede registrar normas propias del municipio/departamento (acuerdos, ordenanzas,
decretos locales de regalías/plan de desarrollo). El indexer las suma a las
nacionales; así el catálogo no queda "quemado" en 36.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NormaTerritorial(Base):
    __tablename__ = "normas_territoriales"

    id:          Mapped[str]  = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    codigo:      Mapped[str]  = mapped_column(String(200), nullable=False, comment="Ej: 'Acuerdo 05 de 2024'")
    territorio:  Mapped[str | None] = mapped_column(String(200), comment="Etiqueta de referencia, ej. 'HUILA / NEIVA'")
    prioridad:   Mapped[int]  = mapped_column(Integer, default=2, comment="1=crítica, 2=importante, 3=complementaria")
    descripcion: Mapped[str | None] = mapped_column(Text)
    activo:      Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    creado_en:   Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
