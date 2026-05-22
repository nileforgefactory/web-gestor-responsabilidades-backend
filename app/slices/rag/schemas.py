"""Esquemas Pydantic del slice RAG (OpenAPI / validación)."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EstrategiaChunk(str, Enum):
    """Estrategia de fragmentación expuesta en formularios multipart."""

    FIJO = "fixed"
    ADAPTATIVO = "adaptive"


class IngestTextRequest(BaseModel):
    """Cuerpo JSON para indexar texto plano."""

    collection_id: str = Field(..., min_length=1, description="ID de colección en Qdrant")
    document_id: str = Field(..., min_length=1, description="Identificador único del documento")
    content: str = Field(..., min_length=1, description="Contenido UTF-8 a fragmentar")
    chunk_size: int = Field(
        default=700,
        ge=200,
        le=8000,
        description="Tamaño aproximado de chunk en caracteres",
    )
    chunk_overlap: int = Field(
        default=120,
        ge=0,
        le=2000,
        description="Solapamiento entre chunks consecutivos en caracteres",
    )
    chunk_strategy: EstrategiaChunk = Field(
        default=EstrategiaChunk.ADAPTATIVO,
        description="fixed = tamaño fijo; adaptive = según tipo de documento/OCR",
    )


class IngestTextResponse(BaseModel):
    """Resultado de una ingesta indexada."""

    collection_id: str
    document_id: str
    chunks_indexed: int = Field(..., description="Fragmentos almacenados en Qdrant")
    chunk_strategy: str | None = Field(None, description="fixed | adaptive aplicado")
    chunk_profile: str | None = Field(None, description="Perfil adaptativo si aplica")
    chunk_size_applied: int | None = None
    chunk_overlap_applied: int | None = None


class IngestArchivoResultado(BaseModel):
    """Resultado por archivo en una ingesta masiva."""

    nombre_archivo: str
    document_id: str
    exito: bool
    chunks_indexados: int = 0
    metodo_extraccion: str | None = Field(
        default=None,
        description="nativo | ocr | hibrido (si aplica)",
    )
    caracteres_extraidos: int | None = None
    error: str | None = None


class IngestMasivaResponse(BaseModel):
    """Resumen de ingesta de múltiples archivos."""

    collection_id: str
    total_archivos: int
    exitosos: int
    fallidos: int
    chunks_totales: int = Field(..., description="Suma de chunks de archivos exitosos")
    resultados: list[IngestArchivoResultado]


class RagSearchRequest(BaseModel):
    """Consulta de búsqueda semántica."""

    collection_ids: list[str] = Field(..., min_length=1, description="Colecciones a consultar")
    query: str = Field(..., min_length=1, description="Texto de la consulta")
    top_k: int = Field(default=5, ge=1, le=25)
    score_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


class RagChunk(BaseModel):
    """Fragmento recuperado de Qdrant con score de similitud."""

    chunk_id: str = Field(..., description="ID del punto vectorial")
    document_id: str
    collection_id: str
    score: float = Field(..., description="Similitud coseno (mayor = más relevante)")
    text: str = Field(..., description="Contenido del fragmento")
    title: str | None = None
    source_filename: str | None = None


class RagSearchResponse(BaseModel):
    """Resultados ordenados por relevancia."""

    query: str
    chunks: list[RagChunk]


class AgentContextRequest(BaseModel):
    """Petición para armar contexto RAG sin invocar el LLM."""

    collection_ids: list[str] = Field(..., min_length=1, description="Colecciones a consultar")
    user_message: str = Field(..., min_length=1, description="Mensaje o pregunta del agente")
    top_k: int = Field(default=6, ge=1, le=30, description="Máximo de chunks a incluir")


class AgentContextResponse(BaseModel):
    """Bloque de contexto listo para inyectar en un prompt externo."""

    user_message: str
    context: str = Field(..., description="Texto concatenado de chunks")
    citations: list[dict[str, str]] = Field(..., description="Metadatos de citas")


class RagCitation(BaseModel):
    """Referencia a un chunk usado en la respuesta de /ask."""

    chunk_id: str
    document_id: str
    collection_id: str
    score: float
    title: str | None = None
    source_filename: str | None = None


class AskRequest(BaseModel):
    """Pregunta conversacional con recuperación RAG."""

    # Un solo `example` mejora compatibilidad Swagger UI (evita cuerpos con `null`
    # que en algunos clientes rompen el contrato esperado por el backend).
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "collection_ids": ["demo_local"],
                "user_message": "Cual es el SLA de primera respuesta para un incidente P1?",
                "top_k": 5,
            },
        },
    )

    collection_ids: list[str] = Field(..., min_length=1)
    user_message: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=25)
    score_threshold: float | None = Field(
        default=None,
        description="Opcional; por defecto usa RAG_DEFAULT_SCORE_THRESHOLD.",
    )


class AskResponse(BaseModel):
    """Respuesta generada por Ollama con citas a chunks."""

    answer: str = Field(..., description="Texto de respuesta del modelo")
    citations: list[RagCitation]
    confidence: float = Field(..., description="Score medio de chunks usados")
    used_chunks: list[str] = Field(..., description="IDs de chunks citados")
    retrieval_empty: bool = Field(False, description="True si no hubo evidencia en Qdrant")