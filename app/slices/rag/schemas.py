from pydantic import BaseModel, ConfigDict, Field


class IngestTextRequest(BaseModel):
    collection_id: str = Field(..., min_length=1, description="Logical knowledge collection")
    document_id: str = Field(..., min_length=1, description="Source document identifier")
    content: str = Field(..., min_length=1, description="Document raw content")
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


class IngestTextResponse(BaseModel):
    collection_id: str
    document_id: str
    chunks_indexed: int


class RagSearchRequest(BaseModel):
    collection_ids: list[str] = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=25)
    score_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


class RagChunk(BaseModel):
    chunk_id: str
    document_id: str
    collection_id: str
    score: float
    text: str
    title: str | None = None
    source_filename: str | None = None


class RagSearchResponse(BaseModel):
    query: str
    chunks: list[RagChunk]


class AgentContextRequest(BaseModel):
    collection_ids: list[str] = Field(..., min_length=1)
    user_message: str = Field(..., min_length=1)
    top_k: int = Field(default=6, ge=1, le=30)


class AgentContextResponse(BaseModel):
    user_message: str
    context: str
    citations: list[dict[str, str]]


class RagCitation(BaseModel):
    chunk_id: str
    document_id: str
    collection_id: str
    score: float
    title: str | None = None
    source_filename: str | None = None


class AskRequest(BaseModel):
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
    answer: str
    citations: list[RagCitation]
    confidence: float
    used_chunks: list[str]
    retrieval_empty: bool = False