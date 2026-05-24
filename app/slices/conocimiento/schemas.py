from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.slices.common.territorio import TERRITORIO_LEN, normalize_territorio, territorio_from_json, territorio_to_json

TipoDocumento = Literal["ley", "decreto", "resolucion", "circular", "pdf", "texto", "otro"]
EstadoDoc     = Literal["pendiente", "procesando", "indexado", "error"]


class ConocimientoCreate(BaseModel):
    nombre:         str
    tipo:           TipoDocumento  = "otro"
    coleccion_id:   str            = "COLOMBIA"
    descripcion:    str | None     = None
    territorio:     list[str | None] | None = Field(
        None,
        min_length=TERRITORIO_LEN,
        max_length=TERRITORIO_LEN,
        description="[País, Departamento, Municipio]",
    )
    archivo_nombre: str | None     = None
    archivo_tamano: int | None     = None
    qdrant_doc_id:  str | None     = None
    chunk_count:    int            = Field(default=0, ge=0)
    estado:         EstadoDoc      = "indexado"
    error_mensaje:  str | None     = None


class ConocimientoUpdate(BaseModel):
    estado:        EstadoDoc | None = None
    chunk_count:   int | None       = None
    qdrant_doc_id: str | None       = None
    error_mensaje: str | None       = None
    territorio:    list[str | None] | None = Field(
        None,
        min_length=TERRITORIO_LEN,
        max_length=TERRITORIO_LEN,
    )


class ConocimientoOut(ConocimientoCreate):
    id:        str
    creado_en: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_validator("territorio", mode="before")
    @classmethod
    def _territorio_from_db(cls, v: object) -> list[str | None] | None:
        if v is None or isinstance(v, list):
            return v if v is None else normalize_territorio(v)
        if isinstance(v, str):
            return territorio_from_json(v)
        return None


def territorio_for_db(territorio: list[str | None] | None) -> str | None:
    if territorio is None:
        return None
    return territorio_to_json(territorio)
