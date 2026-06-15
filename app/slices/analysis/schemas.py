"""Esquemas Pydantic del slice de análisis (OpenAPI / validación)."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProfundidadAnalisis(str, Enum):
    """Nivel de exhaustividad del pipeline de agentes."""

    BASICO = "basico"
    ESTANDAR = "estandar"
    PROFUNDO = "profundo"


class NivelTerritorial(str, Enum):
    """Nivel territorial para contexto de prompts."""

    NACIONAL = "nacional"
    DEPARTAMENTAL = "departamental"
    MUNICIPAL = "municipal"
    SECTORIAL = "sectorial"


class AnalisisDocumentoResponse(BaseModel):
    """Resultado consolidado del análisis de un documento."""

    plan_id: str | None = Field(None, description="ID en MySQL si se persistió")
    document_id: str = Field(..., description="ID del documento en Qdrant")
    collection_id: str = Field(..., description="Colección donde se indexó el plan")
    metodo_extraccion: str = Field(..., description="nativo | ocr | hibrido")
    caracteres_extraidos: int = Field(..., ge=0)
    chunks_indexados: int = Field(..., ge=0)
    chunk_strategy: str | None = None
    chunk_profile: str | None = None
    responsabilidades: list[dict[str, Any]] = Field(default_factory=list)
    leyes: list[dict[str, Any]] = Field(default_factory=list)
    actores: list[dict[str, Any]] = Field(default_factory=list)
    brechas: list[dict[str, Any]] = Field(default_factory=list)
    matriz: list[dict[str, Any]] = Field(default_factory=list)
    iteraciones_coordinador: int = Field(0, ge=0)
    guardado_en_mysql: bool = False


class EventoAnalisis(BaseModel):
    """Evento SSE emitido durante el análisis en streaming."""

    type: str = Field(..., description="log | agent_start | agent_done | coordinator_decision | done | error | heartbeat")
    msg: str | None = None
    agent: str | None = None
    count: int | None = None
    accion: str | None = None
    razon: str | None = None
    confianza: float | None = None
    confianza_objetiva: float | None = None
    metricas: dict[str, Any] | None = None
    error: str | None = None
    plan_id: str | None = None
    session_id: str | None = None
    result: AnalisisDocumentoResponse | None = None
