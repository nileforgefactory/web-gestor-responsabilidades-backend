from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación cargada desde variables de entorno y `.env`."""

    app_name: str = "Agentic RAG API"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rag_chunks"
    vector_size: int = 768

    use_ollama: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_chat_model: str = "llama3.2:3b"

    ingest_embed_concurrency: int = 4
    rag_default_score_threshold: float = 0.25

    # MySQL — opcional; si está vacío las rutas DB devuelven 503
    # Formato: mysql+aiomysql://usuario:clave@host:puerto/base_datos?charset=utf8mb4
    mysql_url: str | None = None

    ocr_enabled: bool = True
    ocr_lang: str = "spa"
    ocr_dpi: int = 200
    ocr_min_chars_per_page: int = 50

    # Subida masiva
    bulk_max_files: int = 50
    bulk_max_file_bytes: int = 52_428_800  # 50 MiB por archivo
    bulk_ingest_concurrency: int = 2

    # Chunking (Sprint 2)
    default_chunk_strategy: str = "adaptive"
    analysis_max_iterations: int = 3
    analysis_confidence_threshold: float = 0.55

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Devuelve instancia singleton de configuración (cacheada)."""
    return Settings()
