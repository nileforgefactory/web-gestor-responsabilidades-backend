"""Esquemas Pydantic para alertas normativas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AlertaNormativaOut(BaseModel):
    id:          int
    plan_id:     str | None
    tipo:        Literal["modificacion", "derogacion", "nueva_norma", "jurisprudencia"]
    titulo:      str
    descripcion: str | None
    norma_ref:   str | None
    severidad:   Literal["alta", "media", "baja"]
    leida:       bool
    creado_en:   datetime

    model_config = ConfigDict(from_attributes=True)


class MarcarLeidaRequest(BaseModel):
    ids: list[int]
