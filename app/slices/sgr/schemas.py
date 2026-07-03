"""Schemas Pydantic para el slice SGR."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Elegibilidad ───────────────────────────────────────────────────────────────

class ElegibilidadResult(BaseModel):
    brecha_id: int
    brecha_titulo: str
    brecha_severidad: str
    brecha_sector: str
    elegible: bool
    condicional: bool = False
    sector_sgr: str
    subsector: str | None = None
    fuente_recomendada: str
    fuente_label: str
    razon: str
    condiciones: list[str] = Field(default_factory=list)
    tipo_inversion: str = ""


# ── Scoring ────────────────────────────────────────────────────────────────────

class ProyectoCandidatoResponse(BaseModel):
    """Proyecto SGR candidato con score de viabilidad — output del Modo 1."""

    # Datos del proyecto
    id: str | None = None
    brecha_id: int
    brecha_titulo: str
    brecha_severidad: str
    nombre: str
    sector_sgr: str
    subsector: str | None = None
    tipo_inversion: str
    fuente_recomendada: str
    fuente_label: str
    razon_elegibilidad: str
    condiciones: list[str] = Field(default_factory=list)

    # Scoring
    score_sgr: float = Field(..., ge=0.0, le=1.0, description="Score de viabilidad 0–1")
    score_severidad: float
    score_alineacion: float
    score_elegibilidad: float
    score_viabilidad: float

    # Semáforo
    semaforo: str = Field(..., description="verde | amarillo | rojo")
    semaforo_label: str

    # Estado y modo
    estado: str = "borrador"
    modo: str = "descubrimiento"

    model_config = ConfigDict(from_attributes=True)


class EvaluarPlanResponse(BaseModel):
    """Respuesta del endpoint GET /sgr/evaluar-plan/{plan_id}."""

    plan_id: str
    municipio_codigo: str | None
    categoria_municipio: str | None
    total_brechas: int
    total_elegibles: int
    total_no_elegibles: int
    proyectos_candidatos: list[ProyectoCandidatoResponse]
    advertencias: list[str] = Field(default_factory=list)
    procesado_en: datetime = Field(default_factory=datetime.utcnow)


# ── Proyecto SGR (CRUD básico) ─────────────────────────────────────────────────

class ProyectoSGROut(BaseModel):
    id: str
    plan_id: str
    brecha_id: int | None
    municipio_codigo: str
    nombre: str
    sector_sgr: str
    subsector_sgr: str | None
    tipo_inversion: str | None
    fuente_sgr: str | None
    score_sgr: float | None
    elegible: bool | None
    razon_elegibilidad: str | None
    cuadrante: str | None
    en_plan: bool | None
    estado: str
    modo: str
    creado_en: datetime
    actualizado_en: datetime
    resultado_duplicidad: dict[str, Any] | None = None
    validacion_costos: dict[str, Any] | None = None
    diagnostico_mga: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Ficha MGA ─────────────────────────────────────────────────────────────────

class FichaMGAOut(BaseModel):
    id: int
    proyecto_id: str
    identificacion: str | None
    preparacion: str | None
    evaluacion: str | None
    programacion: str | None
    campos_completos: int
    modelo_usado: str | None
    generado_en: datetime
    actualizado_en: datetime

    model_config = ConfigDict(from_attributes=True)
