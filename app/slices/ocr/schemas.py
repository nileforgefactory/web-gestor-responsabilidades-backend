from enum import Enum

from pydantic import BaseModel, Field


class MetodoExtraccion(str, Enum):
    NATIVO = "nativo"
    OCR = "ocr"
    HIBRIDO = "hibrido"


class ExtraccionArchivoResultado(BaseModel):
    nombre_archivo: str
    exito: bool
    metodo_extraccion: MetodoExtraccion | None = None
    paginas: int = 0
    caracteres: int = 0
    paginas_ocr: int = 0
    paginas_nativas: int = 0
    confianza_ocr_promedio: float | None = None
    texto: str | None = Field(
        default=None,
        description="Texto completo; omitido si incluir_texto=false en extracción masiva",
    )
    error: str | None = None


class ExtraccionMasivaResponse(BaseModel):
    total_archivos: int
    exitosos: int
    fallidos: int
    resultados: list[ExtraccionArchivoResultado]


class ExtraccionDocumentoResponse(BaseModel):
    """Resultado de extracción de texto (sin indexar en Qdrant)."""

    texto: str = Field(description="Texto completo extraído del documento")
    nombre_archivo: str
    metodo_extraccion: MetodoExtraccion
    paginas: int = Field(ge=0, description="Número de páginas procesadas")
    caracteres: int = Field(ge=0, description="Longitud del texto resultante")
    paginas_ocr: int = Field(
        default=0,
        ge=0,
        description="Páginas en las que se aplicó OCR",
    )
    paginas_nativas: int = Field(
        default=0,
        ge=0,
        description="Páginas con texto nativo del PDF",
    )
    confianza_ocr_promedio: float | None = Field(
        default=None,
        description="Confianza media Tesseract (0–100), si aplica",
    )
