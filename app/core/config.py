from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación cargada desde variables de entorno y `.env`."""

    app_name: str = "Agentic RAG API"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Logging: INFO en producción; DEBUG solo si hace falta
    app_log_level: str = "INFO"
    scraper_log_level: str | None = None
    ollama_log_llm_bodies: bool = False
    sqlalchemy_log_engine: bool = False

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
    # pool_pre_ping con aiomysql async falla en algunas versiones (ping/reconnect)
    mysql_pool_pre_ping: bool = False

    # Redis — opcional; si está vacío las sesiones SSE no se persisten
    # Formato: redis://host:puerto/db
    redis_url: str | None = None

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

    # Scraper de normativa (búsqueda en red + validación IA)
    scraper_collection_id: str = "normas_legales"
    scraper_search_max_results: int = 8
    scraper_search_query_suffix: str = "normativa PDF"
    scraper_validation_min_confidence: float = 0.72
    scraper_validation_text_max_chars: int = 12_000
    scraper_fetch_timeout_sec: float = 45.0
    scraper_fetch_max_bytes: int = 25_000_000
    # Reintentos de descarga ante timeout/red; SSL puede reintentarse sin verificar certificado
    scraper_fetch_retries: int = 2
    scraper_fetch_verify_ssl: bool = True
    scraper_fetch_ssl_fallback: bool = True
    scraper_min_extracted_chars: int = 200
    scraper_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    scraper_search_query_variants: int = 3
    # Dominios permitidos (coma-separados); vacío = sin restricción
    scraper_allowed_domains: str = ""
    # Proveedor: duckduckgo | tavily
    scraper_search_provider: str = "duckduckgo"
    scraper_tavily_api_key: str | None = None
    # Normas procesadas en paralelo (asyncio; no saturar Ollama ni búsqueda)
    scraper_max_concurrency: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Devuelve instancia singleton de configuración (cacheada)."""
    return Settings()
