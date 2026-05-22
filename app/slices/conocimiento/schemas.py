from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TipoDocumento = Literal["ley", "decreto", "resolucion", "circular", "pdf", "texto", "otro"]
EstadoDoc     = Literal["pendiente", "procesando", "indexado", "error"]


class ConocimientoCreate(BaseModel):
    nombre:         str
    tipo:           TipoDocumento  = "otro"
    coleccion_id:   str            = "normas_legales"
    descripcion:    str | None     = None
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


class ConocimientoOut(ConocimientoCreate):
    id:        str
    creado_en: datetime
    model_config = ConfigDict(from_attributes=True)
