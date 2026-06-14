"""Modelos SQLAlchemy para el slice de Planes."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Planes ────────────────────────────────────────────────────────────────

class Plane(Base):
    __tablename__ = "planes"
    __table_args__ = (
        Index("idx_planes_nivel",  "nivel"),
        Index("idx_planes_estado", "estado"),
    )

    id:             Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    titulo:         Mapped[str]      = mapped_column(String(500), nullable=False)
    nombre_corto:   Mapped[str | None] = mapped_column(String(100))
    entidad:        Mapped[str | None] = mapped_column(String(300))
    entidad_icono:  Mapped[str]      = mapped_column(String(10), default="🏛️")
    nivel:          Mapped[str]      = mapped_column(
        Enum("nacional", "departamental", "municipal", "sectorial"),
        nullable=False,
    )
    periodo:        Mapped[str | None] = mapped_column(String(50))
    estado:         Mapped[str]      = mapped_column(
        Enum("cargando", "analizando", "analizado", "en-proceso", "archivado"),
        default="cargando",
    )
    descripcion:    Mapped[str | None] = mapped_column(Text)
    archivo_nombre: Mapped[str | None] = mapped_column(String(500))
    qdrant_doc_id:  Mapped[str | None] = mapped_column(String(100))

    resp_total:     Mapped[int]   = mapped_column(Integer, default=0)
    leyes_total:    Mapped[int]   = mapped_column(Integer, default=0)
    actores_total:  Mapped[int]   = mapped_column(Integer, default=0)
    brechas_total:  Mapped[int]   = mapped_column(Integer, default=0)
    avance_pct:     Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    creado_en:      Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # ── Relaciones ──
    sectores:          Mapped[list[PlanSector]]        = relationship(back_populates="plan", cascade="all, delete-orphan")
    actores:           Mapped[list[PlanActor]]         = relationship(back_populates="plan", cascade="all, delete-orphan")
    responsabilidades: Mapped[list[Responsabilidad]]   = relationship(back_populates="plan", cascade="all, delete-orphan")
    brechas:           Mapped[list[Brecha]]            = relationship(back_populates="plan", cascade="all, delete-orphan")
    matriz:            Mapped[list[MatrizCompetencia]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    normas:            Mapped[list[PlanNorma]]         = relationship(back_populates="plan", cascade="all, delete-orphan")


# ── Sectores ──────────────────────────────────────────────────────────────

class PlanSector(Base):
    __tablename__ = "plan_sectores"

    id:            Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id:       Mapped[str]        = mapped_column(String(36), ForeignKey("planes.id", ondelete="CASCADE"), nullable=False, index=True)
    sector:        Mapped[str]        = mapped_column(String(200), nullable=False)
    icono:         Mapped[str | None] = mapped_column(String(10))
    cobertura_pct: Mapped[float]      = mapped_column(Numeric(5, 2), default=0)

    plan: Mapped[Plane] = relationship(back_populates="sectores")


# ── Actores ───────────────────────────────────────────────────────────────

class PlanActor(Base):
    __tablename__ = "plan_actores"

    id:            Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id:       Mapped[str]        = mapped_column(String(36), ForeignKey("planes.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre:        Mapped[str]        = mapped_column(String(300), nullable=False)
    tipo:          Mapped[str]        = mapped_column(
        Enum(
            "ejecutor", "beneficiario", "financiador", "coordinador",
            "regulador", "aliado", "operador", "supervisor",
            "tomador_decision", "participante", "apoyo_tecnico", "control",
            "otro",
        ),
        default="otro",
    )
    icono:         Mapped[str | None] = mapped_column(String(10))
    resp_count:    Mapped[int]        = mapped_column(Integer, default=0)
    nivel:         Mapped[str | None] = mapped_column(String(50))
    sector:        Mapped[str | None] = mapped_column(String(200))
    badge_label:   Mapped[str | None] = mapped_column(String(100))
    badge_variant: Mapped[str]        = mapped_column(String(20), default="blue")
    destacado:     Mapped[bool]       = mapped_column(Boolean, default=False)

    plan:          Mapped[Plane]                  = relationship(back_populates="actores")
    competencias:  Mapped[list[ActorCompetencia]] = relationship(back_populates="actor", cascade="all, delete-orphan")


# ── Competencias de un Actor ──────────────────────────────────────────────

class ActorCompetencia(Base):
    __tablename__ = "actor_competencias"

    id:       Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id:  Mapped[str]        = mapped_column(String(36), ForeignKey("planes.id",       ondelete="CASCADE"), nullable=False, index=True)
    actor_id: Mapped[int]        = mapped_column(Integer,   ForeignKey("plan_actores.id",  ondelete="CASCADE"), nullable=False, index=True)
    titulo:   Mapped[str]        = mapped_column(String(500), nullable=False)
    sector:   Mapped[str | None] = mapped_column(String(200))

    actor: Mapped[PlanActor] = relationship(back_populates="competencias")


# ── Responsabilidades ─────────────────────────────────────────────────────

class Responsabilidad(Base):
    __tablename__ = "responsabilidades"
    __table_args__ = (
        Index("idx_resp_plan",   "plan_id"),
        Index("idx_resp_sector", "sector"),
    )

    id:               Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id:          Mapped[str]        = mapped_column(String(36), ForeignKey("planes.id", ondelete="CASCADE"), nullable=False)
    titulo:           Mapped[str]        = mapped_column(String(500), nullable=False)
    descripcion:      Mapped[str | None] = mapped_column(Text)
    sector:           Mapped[str | None] = mapped_column(String(200))
    tipo:             Mapped[str]        = mapped_column(Enum("P", "C", "S", "N"), default="P")
    referencia_legal: Mapped[str | None] = mapped_column(String(200))
    icono:            Mapped[str]        = mapped_column(String(10), default="✅")

    plan: Mapped[Plane] = relationship(back_populates="responsabilidades")


# ── Brechas ───────────────────────────────────────────────────────────────

class Brecha(Base):
    __tablename__ = "brechas"

    id:               Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id:          Mapped[str]        = mapped_column(String(36), ForeignKey("planes.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo:           Mapped[str]        = mapped_column(String(500), nullable=False)
    descripcion:      Mapped[str | None] = mapped_column(Text)
    tipo:             Mapped[str]        = mapped_column(
        Enum("critica", "duplicidad", "indefinido", "sin_responsable"), default="critica"
    )
    severidad:        Mapped[str]        = mapped_column(Enum("alta", "media", "baja"), default="alta")
    referencia_legal: Mapped[str | None] = mapped_column(String(200))
    icono:            Mapped[str]        = mapped_column(String(10), default="🚨")

    plan: Mapped[Plane] = relationship(back_populates="brechas")


# ── Matriz de Competencias ────────────────────────────────────────────────

class MatrizCompetencia(Base):
    __tablename__ = "matriz_competencias"

    id:                   Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id:              Mapped[str]        = mapped_column(String(36), ForeignKey("planes.id", ondelete="CASCADE"), nullable=False, index=True)
    competencia:          Mapped[str]        = mapped_column(String(300), nullable=False)
    ley_base:             Mapped[str | None] = mapped_column(String(200))
    nacion:               Mapped[str]        = mapped_column(Enum("P", "C", "S", "N"), default="N")
    departamento:         Mapped[str]        = mapped_column(Enum("P", "C", "S", "N"), default="N")
    municipio:            Mapped[str]        = mapped_column(Enum("P", "C", "S", "N"), default="N")
    especializado:        Mapped[str]        = mapped_column(Enum("P", "C", "S", "N"), default="N")
    brecha:               Mapped[str]        = mapped_column(
        Enum("ok", "critica", "duplicidad", "indefinido"), default="ok"
    )
    actores_vinculados:   Mapped[str | None] = mapped_column(Text)  # JSON: [{nombre, nivel, tipo}]

    plan: Mapped[Plane] = relationship(back_populates="matriz")


# ── Normas/Leyes por plan ─────────────────────────────────────────────────

class PlanNorma(Base):
    __tablename__ = "plan_normas"
    __table_args__ = (
        Index("idx_norma_plan", "plan_id"),
        Index("idx_norma_tipo", "tipo"),
    )

    id:            Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id:       Mapped[str]        = mapped_column(String(36), ForeignKey("planes.id", ondelete="CASCADE"), nullable=False)
    norma_codigo:  Mapped[str | None] = mapped_column(String(100))
    titulo:        Mapped[str]        = mapped_column(String(500), nullable=False)
    articulos:     Mapped[str | None] = mapped_column(String(200))
    extracto:      Mapped[str | None] = mapped_column(Text)
    tipo:          Mapped[str]        = mapped_column(
        Enum("ley", "decreto", "resolucion", "circular", "politica", "conpes", "ordenanza", "acuerdo", "otro"), default="ley"
    )
    vigente:       Mapped[bool]       = mapped_column(Boolean, default=True)
    advertencia:   Mapped[str | None] = mapped_column(String(300))
    relevancia:    Mapped[int]        = mapped_column(Integer, default=80)

    plan: Mapped[Plane] = relationship(back_populates="normas")
