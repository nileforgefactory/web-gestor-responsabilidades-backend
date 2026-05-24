"""Esquemas del scraper de normativa (OpenAPI / validación)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.slices.common.territorio import TERRITORIO_LEN, normalize_territorio

EstadoNormaScraper = Literal["indexada", "no_encontrada", "no_indexada", "error"]


class ScraperBuscarRequest(BaseModel):
    """Solicitud de búsqueda e indexación de normas por nombre o referencia."""

    normas: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Referencias normativas (ej. 'Ley 1523 de 2012', 'Decreto 1077 art. 5').",
    )


class ValidacionNormaOut(BaseModel):
    es_documento_esperado: bool
    confianza: float = Field(ge=0.0, le=1.0)
    codigo_detectado: str | None = None
    motivo: str | None = None
    advertencias: list[str] = Field(default_factory=list)
    territorio: list[str | None] = Field(
        default_factory=lambda: ["COLOMBIA", None, None],
        min_length=TERRITORIO_LEN,
        max_length=TERRITORIO_LEN,
        description=(
            "Ámbito territorial [País, Departamento, Municipio]. "
            "Nacional: [COLOMBIA, null, null]. Departamental: [COLOMBIA, HUILA, null]. "
            "Municipal: [COLOMBIA, HUILA, NEIVA]."
        ),
        json_schema_extra={"example": ["COLOMBIA", "HUILA", None]},
    )

    @field_validator("territorio", mode="before")
    @classmethod
    def _norm_territorio(cls, v: object) -> list[str | None]:
        return normalize_territorio(v)


class NormaScraperResultado(BaseModel):
    norma: str
    estado: EstadoNormaScraper
    url: str | None = None
    document_id: str | None = None
    chunks_indexados: int = 0
    territorio: list[str | None] | None = Field(
        None,
        min_length=TERRITORIO_LEN,
        max_length=TERRITORIO_LEN,
        description="Territorio inferido por IA al validar (si aplica).",
    )
    validacion: ValidacionNormaOut | None = None
    motivo: str | None = Field(
        None,
        description="Detalle cuando no se indexó o no se encontró.",
    )
    urls_intentadas: list[str] = Field(default_factory=list)


class ScraperResumen(BaseModel):
    solicitadas: int
    indexadas: int
    no_encontradas: int
    no_indexadas: int
    errores: int = 0
    concurrencia: int = Field(
        1,
        description="Número máximo de normas procesadas en paralelo en esta solicitud.",
    )


class ScraperBuscarResponse(BaseModel):
    resumen: ScraperResumen
    resultados: list[NormaScraperResultado]
