"""Esquemas Pydantic para entrada/salida del slice Planes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ─── Sub-entidades ────────────────────────────────────────────────────────

class SectorIn(BaseModel):
    sector:        str
    icono:         str | None = None
    cobertura_pct: float      = 0.0


class SectorOut(SectorIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ActorIn(BaseModel):
    nombre:        str
    tipo:          Literal["principal", "concurrente", "subsidiario", "otro"] = "otro"
    icono:         str | None = None
    resp_count:    int        = 0
    badge_label:   str | None = None
    badge_variant: str        = "blue"
    destacado:     bool       = False


class ActorOut(ActorIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ResponsabilidadIn(BaseModel):
    titulo:           str
    descripcion:      str | None = None
    sector:           str | None = None
    tipo:             Literal["P", "C", "S", "N"] = "P"
    referencia_legal: str | None = None
    icono:            str        = "✅"


class ResponsabilidadOut(ResponsabilidadIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class BrechaIn(BaseModel):
    titulo:           str
    descripcion:      str | None = None
    tipo:             Literal["critica", "duplicidad", "indefinido", "sin_responsable"] = "critica"
    severidad:        Literal["alta", "media", "baja"] = "alta"
    referencia_legal: str | None = None
    icono:            str        = "🚨"


class BrechaOut(BrechaIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class MatrizIn(BaseModel):
    competencia:   str
    ley_base:      str | None                        = None
    nacion:        Literal["P", "C", "S", "N"]      = "N"
    departamento:  Literal["P", "C", "S", "N"]      = "N"
    municipio:     Literal["P", "C", "S", "N"]      = "N"
    especializado: Literal["P", "C", "S", "N"]      = "N"
    brecha:        Literal["ok", "critica", "duplicidad", "indefinido"] = "ok"


class MatrizOut(MatrizIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class NormaIn(BaseModel):
    norma_codigo:  str | None = None
    titulo:        str
    articulos:     str | None = None
    extracto:      str | None = None
    tipo:          Literal["ley", "decreto", "resolucion", "circular", "otro"] = "ley"
    vigente:       bool       = True
    advertencia:   str | None = None
    relevancia:    int        = Field(default=80, ge=0, le=100)


class NormaOut(NormaIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ─── Plane ────────────────────────────────────────────────────────────────

NivelTerritorial = Literal["nacional", "departamental", "municipal", "sectorial"]
EstadoPlan       = Literal["cargando", "analizando", "analizado", "en-proceso", "archivado"]


class PlanCreate(BaseModel):
    titulo:         str
    nombre_corto:   str | None          = None
    entidad:        str | None          = None
    entidad_icono:  str                 = "🏛️"
    nivel:          NivelTerritorial
    periodo:        str | None          = None
    estado:         EstadoPlan          = "cargando"
    descripcion:    str | None          = None
    archivo_nombre: str | None          = None
    qdrant_doc_id:  str | None          = None
    resp_total:     int                 = 0
    leyes_total:    int                 = 0
    actores_total:  int                 = 0
    brechas_total:  int                 = 0
    avance_pct:     float               = 0.0
    # sub-entities opcionales al crear
    sectores:          list[SectorIn]          = []
    actores:           list[ActorIn]           = []
    responsabilidades: list[ResponsabilidadIn] = []
    brechas:           list[BrechaIn]          = []
    matriz:            list[MatrizIn]          = []
    normas:            list[NormaIn]           = []


class PlanUpdate(BaseModel):
    """Actualización parcial — solo los campos enviados se modifican."""
    titulo:         str | None       = None
    nombre_corto:   str | None       = None
    entidad:        str | None       = None
    entidad_icono:  str | None       = None
    nivel:          NivelTerritorial | None = None
    periodo:        str | None       = None
    estado:         EstadoPlan | None = None
    descripcion:    str | None       = None
    qdrant_doc_id:  str | None       = None
    resp_total:     int | None       = None
    leyes_total:    int | None       = None
    actores_total:  int | None       = None
    brechas_total:  int | None       = None
    avance_pct:     float | None     = None


class PlanSummary(BaseModel):
    """Versión ligera para listados (sin sub-entidades)."""
    id:             str
    titulo:         str
    nombre_corto:   str | None
    entidad:        str | None
    entidad_icono:  str
    nivel:          str
    periodo:        str | None
    estado:         str
    resp_total:     int
    leyes_total:    int
    actores_total:  int
    brechas_total:  int
    avance_pct:     float
    creado_en:      datetime
    actualizado_en: datetime
    sectores:       list[SectorOut] = []
    model_config = ConfigDict(from_attributes=True)


class PlanDetail(PlanSummary):
    """Versión completa con todas las sub-entidades."""
    descripcion:       str | None
    archivo_nombre:    str | None
    qdrant_doc_id:     str | None
    actores:           list[ActorOut]           = []
    responsabilidades: list[ResponsabilidadOut] = []
    brechas:           list[BrechaOut]          = []
    matriz:            list[MatrizOut]          = []
    normas:            list[NormaOut]           = []
    model_config = ConfigDict(from_attributes=True)
