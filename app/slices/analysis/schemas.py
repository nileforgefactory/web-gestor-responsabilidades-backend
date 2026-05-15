"""Esquemas Pydantic para el slice de análisis agentico."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalyzePlanRequest(BaseModel):
    plan_id: str = Field(..., description="ID del plan a analizar (UUID)")
    collection_id: str = Field(..., description="Colección Qdrant con los chunks del plan")
    nivel: Literal["nacional", "departamental", "municipal", "sectorial"] = "municipal"
    depth: Literal["basico", "estandar", "profundo"] = "estandar"
    sectores: list[str] = Field(default=[], description="Sectores declarados en el plan")
    entidad: str = Field(default="", description="Nombre de la entidad territorial")


class AnalysisStartResponse(BaseModel):
    session_id: str
    plan_id: str
    message: str = "Análisis iniciado. Conecta al stream SSE para ver el progreso."


class CoordinatorDecision(BaseModel):
    accion: Literal["finalizar", "buscar_mas", "reanalizar_sector"]
    razon: str
    query: str | None = None
    sector: str | None = None
    confianza: float = 1.0


class AnalysisEvent(BaseModel):
    type: str
    msg: str | None = None
    agent: str | None = None
    count: int | None = None
    error: str | None = None
    plan_id: str | None = None
    session_id: str | None = None
    accion: str | None = None
    razon: str | None = None
    confianza: float | None = None
    data: dict[str, Any] | None = None
