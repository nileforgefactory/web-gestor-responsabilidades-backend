from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


EstadoTarea = Literal["idle", "running", "completed", "cancelled", "error"]


class BackgroundScraperEstado(BaseModel):
    estado: EstadoTarea
    iniciado_en: datetime | None = None
    finalizado_en: datetime | None = None
    duracion_max_min: int
    normas_total: int = 0
    normas_procesadas: int = 0
    normas_indexadas: int = 0
    normas_fallidas: int = 0
    norma_actual: str | None = None
    error: str | None = None


class BackgroundScraperIniciarRequest(BaseModel):
    duracion_min: int | None = None          # sobreescribe la config si se envía
    prioridad_max: int = 2                   # 1=críticas, 2=importantes, 3=todas
    pais: str = "COLOMBIA"
    solo_faltantes: bool = True              # omite normas ya indexadas en MySQL


class NormaTerritorialCreate(BaseModel):
    codigo: str                              # ej. "Acuerdo 05 de 2024"
    territorio: str | None = None            # etiqueta ref, ej. "HUILA / NEIVA"
    prioridad: int = 2
    descripcion: str | None = None


class NormaTerritorialOut(BaseModel):
    id: str
    codigo: str
    territorio: str | None = None
    prioridad: int
    descripcion: str | None = None
    activo: bool
    creado_en: datetime | None = None

    class Config:
        from_attributes = True


class DescubrirNormasRequest(BaseModel):
    municipio: str | None = None
    departamento: str | None = None
    tema: str | None = None


class DescubrirNormasResponse(BaseModel):
    descubiertas: list[str] = []
    agregadas: list[str] = []
    ya_presentes: list[str] = []
