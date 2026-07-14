"""Modelos SQLAlchemy para el slice SGR — Caja de Herramientas SGR Cat. 5 y 6."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Costos de referencia regional ─────────────────────────────────────────────

class CostoReferenciaSGR(Base):
    """Precios unitarios de referencia por tipo de inversión y región.

    Fuentes: DNP precios unitarios sectoriales, histórico SUIFP-SGR, índices DANE.
    """
    __tablename__ = "costos_referencia_sgr"
    __table_args__ = (
        Index("idx_costos_sector_region", "sector_sgr", "region_geografica"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_sgr: Mapped[str] = mapped_column(String(80), nullable=False)
    tipo_inversion: Mapped[str] = mapped_column(String(120), nullable=False)
    unidad_medida: Mapped[str] = mapped_column(String(50), nullable=False)
    region_geografica: Mapped[str] = mapped_column(
        Enum("Andes", "Caribe", "Pacifico", "Amazonia", "Orinoquia", name="region_geo_enum"),
        nullable=False,
    )
    departamento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valor_minimo: Mapped[float] = mapped_column(Float, nullable=False)
    valor_promedio: Mapped[float] = mapped_column(Float, nullable=False)
    valor_maximo: Mapped[float] = mapped_column(Float, nullable=False)
    fuente: Mapped[str] = mapped_column(String(200), nullable=False)
    anio_referencia: Mapped[int] = mapped_column(Integer, nullable=False)
    vigente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ── Proyecto SGR ───────────────────────────────────────────────────────────────

class ProyectoSGR(Base):
    """Proyecto de inversión formulado o evaluado para el SGR.

    Puede originarse por descubrimiento (Modo 1) o por evaluación inversa (Modo 2).
    """
    __tablename__ = "proyectos_sgr"
    __table_args__ = (
        Index("idx_proyecto_plan", "plan_id"),
        Index("idx_proyecto_municipio", "municipio_codigo"),
        Index("idx_proyecto_estado", "estado"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planes.id", ondelete="CASCADE"), nullable=False
    )
    brecha_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("brechas.id", ondelete="SET NULL"), nullable=True,
        comment="Brecha origen (Modo 1) — nulo si viene de evaluación inversa"
    )

    municipio_codigo: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="Código DIVIPOLA"
    )
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion_problema: Mapped[str | None] = mapped_column(Text)
    sector_sgr: Mapped[str] = mapped_column(String(80), nullable=False)
    subsector_sgr: Mapped[str | None] = mapped_column(String(120))
    tipo_inversion: Mapped[str | None] = mapped_column(Text)

    # Fuente de financiamiento principal detectada
    fuente_sgr: Mapped[str | None] = mapped_column(
        Enum(
            "inversion_local",
            "asignacion_directa",
            "inversion_regional",
            "ctei",
            "paz",
            "ambiental",
            name="fuente_sgr_enum",
        ),
        nullable=True,
    )

    # Scoring de viabilidad (0.0–1.0)
    score_sgr: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_severidad: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_alineacion: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_elegibilidad: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_viabilidad: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Flags de elegibilidad
    elegible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    razon_elegibilidad: Mapped[str | None] = mapped_column(Text)

    # Cuadrante Modo 2 (cuando aplica)
    cuadrante: Mapped[str | None] = mapped_column(
        Enum(
            "optimo",
            "bien_justificado",
            "atractivo_con_riesgo",
            "reformular",
            name="cuadrante_sgr_enum",
        ),
        nullable=True,
    )

    # Resultados de verificaciones (JSON)
    resultado_duplicidad: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Resultado agente_duplicidad"
    )
    validacion_costos: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Resultado agente_costos"
    )
    diagnostico_mga: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Diagnóstico estructural MGA (Modo 2)"
    )

    # ¿Está en el Plan de Desarrollo?
    en_plan: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    chunks_respaldo: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON: IDs de chunks que respaldan el proyecto en el plan"
    )
    texto_inclusion_sugerido: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Texto sugerido para inclusión en el plan vía Acuerdo"
    )

    # Estado de la máquina de estados del proyecto
    estado: Mapped[str] = mapped_column(
        Enum(
            "borrador",
            "diagnosticado",
            "pendiente_plan",
            "en_plan",
            "pre_validado",
            "listo_dnp",
            "enviado_dnp",
            "aprobado",
            "rechazado",
            name="estado_proyecto_sgr_enum",
        ),
        nullable=False,
        default="borrador",
    )

    # Modo de origen
    modo: Mapped[str] = mapped_column(
        Enum("descubrimiento", "evaluacion_inversa", name="modo_sgr_enum"),
        nullable=False,
        default="descubrimiento",
    )

    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    guardado_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
        comment="NULL = borrador de sesion; timestamp = guardado explicito por el usuario",
    )

    # Relaciones
    ficha_mga: Mapped[FichaMGA | None] = relationship(
        "FichaMGA", back_populates="proyecto", uselist=False, cascade="all, delete-orphan"
    )


# ── Ficha MGA ─────────────────────────────────────────────────────────────────

class FichaMGA(Base):
    """Texto pre-generado de las 4 secciones MGA Web para un proyecto elegible."""

    __tablename__ = "fichas_mga"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proyecto_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("proyectos_sgr.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Las 4 secciones MGA Web (texto generado por agente_mga)
    identificacion: Mapped[str | None] = mapped_column(
        Text, comment="Sec. 1 MGA: nombre, sector, municipio, competencia"
    )
    preparacion: Mapped[str | None] = mapped_column(
        Text, comment="Sec. 2 MGA: problema central, árbol causas/efectos, población"
    )
    evaluacion: Mapped[str | None] = mapped_column(
        Text, comment="Sec. 3 MGA: indicadores de producto y resultado, costo/beneficiario"
    )
    programacion: Mapped[str | None] = mapped_column(
        Text, comment="Sec. 4 MGA: fuentes, actividades, cronograma, sostenibilidad"
    )

    # Metadatos de calidad
    campos_completos: Mapped[int] = mapped_column(Integer, default=0, comment="0–4")
    modelo_usado: Mapped[str | None] = mapped_column(String(100))
    tokens_usados: Mapped[int | None] = mapped_column(Integer)

    generado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    chat_historial: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="Historial de chat de edición: lista de {role, texto, timestamp}"
    )

    cobertura_preguntas: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "Cobertura del instrumento MGA (46 preguntas de los módulos 1-4, de las 50 "
            "totales — las 4 de Presentación no aplican a la ficha): lista de "
            "{numero, modulo, pregunta, estado} — estado: respondida | parcial | no_respondida"
        ),
    )

    checklist_verificacion: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "Evaluación IA del checklist final de verificación (20 de los 22 ítems, "
            "excluye 2 no verificables desde el texto): lista de "
            "{numero, modulo, item, cumple, motivo}"
        ),
    )

    proyecto: Mapped[ProyectoSGR] = relationship("ProyectoSGR", back_populates="ficha_mga")


# ── Catálogo de proyectos de la Matriz SGR (GESPROY/DNP) ──────────────────────

class ProyectoMatrizSGR(Base):
    """
    Catálogo liviano (MySQL) de los proyectos SGR ya aprobados que se cargan desde
    el Excel "Balance de Seguimiento a las Inversiones del SGR" (GESPROY/DNP) y se
    indexan en Qdrant para verificación de duplicidad (agente_duplicidad.py).

    Se repuebla por completo en cada carga exitosa del Excel (la tabla siempre
    refleja el último archivo subido). `qdrant_doc_id` referencia el documento
    indexado en la colección lógica "proyectos_sgr" de Qdrant.
    """

    __tablename__ = "proyectos_matriz_sgr"

    id:               Mapped[str]  = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    bpin:             Mapped[str | None] = mapped_column(String(50), index=True)
    nombre:           Mapped[str]  = mapped_column(String(500), index=True)
    municipio:        Mapped[str | None] = mapped_column(Text)
    departamento:     Mapped[str | None] = mapped_column(String(150), index=True)
    sector:           Mapped[str | None] = mapped_column(String(150))
    estado:           Mapped[str | None] = mapped_column(String(100))
    valor_sgr:        Mapped[str | None] = mapped_column(String(100))
    fecha_aprobacion: Mapped[str | None] = mapped_column(String(50))
    qdrant_doc_id:    Mapped[str | None] = mapped_column(String(200))
    creado_en:        Mapped[datetime]   = mapped_column(DateTime, server_default=func.now())
