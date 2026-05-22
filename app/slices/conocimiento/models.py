"""Modelo SQLAlchemy para la Base de Conocimiento RAG."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BaseConocimiento(Base):
    __tablename__ = "base_conocimiento"

    id:             Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    nombre:         Mapped[str]      = mapped_column(String(500), nullable=False)
    tipo:           Mapped[str]      = mapped_column(
        Enum("ley", "decreto", "resolucion", "circular", "pdf", "texto", "otro"),
        default="otro",
    )
    coleccion_id:   Mapped[str]      = mapped_column(String(100), default="normas_legales")
    descripcion:    Mapped[str | None] = mapped_column(Text)
    archivo_nombre: Mapped[str | None] = mapped_column(String(500))
    archivo_tamano: Mapped[int | None] = mapped_column(Integer)
    qdrant_doc_id:  Mapped[str | None] = mapped_column(String(100))
    chunk_count:    Mapped[int]      = mapped_column(Integer, default=0)
    estado:         Mapped[str]      = mapped_column(
        Enum("pendiente", "procesando", "indexado", "error"),
        default="pendiente",
        index=True,
    )
    error_mensaje:  Mapped[str | None] = mapped_column(Text)
    creado_en:      Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
