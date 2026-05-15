from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProfundidadAnalisis(str, Enum):
    BASICO = "basico"
    ESTANDAR = "estandar"
    PROFUNDO = "profundo"


class NivelTerritorial(str, Enum):
    NACIONAL = "nacional"
    DEPARTAMENTAL = "departamental"
    MUNICIPAL = "municipal"
    SECTORIAL = "sectorial"


class AnalisisDocumentoResponse(BaseModel):
    plan_id: str | None = None
    document_id: str
    collection_id: str
    metodo_extraccion: str
    caracteres_extraidos: int
    chunks_indexados: int
    chunk_strategy: str | None = None
    chunk_profile: str | None = None
    responsabilidades: list[dict[str, Any]] = Field(default_factory=list)
    leyes: list[dict[str, Any]] = Field(default_factory=list)
    actores: list[dict[str, Any]] = Field(default_factory=list)
    brechas: list[dict[str, Any]] = Field(default_factory=list)
    matriz: list[dict[str, Any]] = Field(default_factory=list)
    iteraciones_coordinador: int = 0
    guardado_en_mysql: bool = False


class EventoAnalisis(BaseModel):
    type: str
    msg: str | None = None
    agent: str | None = None
    count: int | None = None
    accion: str | None = None
    razon: str | None = None
    confianza: float | None = None
    error: str | None = None
    plan_id: str | None = None
    session_id: str | None = None
    result: AnalisisDocumentoResponse | None = None
