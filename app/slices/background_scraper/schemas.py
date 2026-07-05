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
