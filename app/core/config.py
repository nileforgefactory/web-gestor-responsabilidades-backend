from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Mismo endpoint que docker-compose (MySQL expuesto en host :3307).
DEFAULT_MYSQL_URL = (
    "mysql+aiomysql://gestor:gestor_pass@localhost:3307/"
    "gestor_responsabilidades?charset=utf8mb4"
)


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

    # Gemini — si se define GEMINI_API_KEY se usa Gemini en lugar de Ollama para chat
    gemini_api_key: str | None = None
    gemini_chat_model: str = "gemini-2.0-flash"
    # Embeddings Gemini: gemini-embedding-001 (reemplaza text-embedding-004, deprecado por Google)
    gemini_embedding_model: str = "gemini-embedding-001"

    @property
    def use_gemini(self) -> bool:
        """True si hay API key de Gemini configurada."""
        return bool((self.gemini_api_key or "").strip())

    # OpenAI — tiene máxima prioridad si está definido
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-4o-mini"

    @property
    def use_openai(self) -> bool:
        return bool((self.openai_api_key or "").strip())

    # OpenRouter — API compatible con OpenAI; tiene prioridad sobre Gemini si está definido
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_chat_model: str = "google/gemini-3.5-flash"

    @property
    def use_openrouter(self) -> bool:
        """True si hay API key de OpenRouter configurada (tiene prioridad sobre Gemini)."""
        return bool((self.openrouter_api_key or "").strip())

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
    # Páginas rasterizadas a la vez en el OCR. Acota el pico de memoria en PDFs
    # escaneados grandes (evita que el proceso se reinicie por consumo de RAM).
    ocr_batch_pages: int = 4

    # Subida masiva
    bulk_max_files: int = 50
    bulk_max_file_bytes: int = 52_428_800  # 50 MiB por archivo
    bulk_ingest_concurrency: int = 2

    # Límite de caracteres para cargue de texto libre (evaluación inversa, texto
    # directo en base de conocimiento, extracción de documentos) — fuerza
    # depuración de la información en vez de pegar informes completos. Ajustable
    # sin redeploy vía env var mientras se define el número final (ref. ficha EBI).
    max_chars_texto_libre: int = 8_000

    # Chunking (Sprint 2)
    default_chunk_strategy: str = "adaptive"
    analysis_max_iterations: int = 3
    analysis_confidence_threshold: float = 0.55

    # Construcción de la matriz de competencias (Agente 5):
    #   "deterministic" → cruce relacional en Python por id_norma (0% alucinación, gratis) [default]
    #   "llm"           → consolidación por LLM con super-contexto + saneamiento JSON
    analysis_matriz_mode: str = "deterministic"

    # Profundidad de lectura del documento por cada agente (cuánto del plan ve el LLM).
    # Con modelos de contexto amplio (Gemini, GPT-4o) conviene subirlos para no perder
    # leyes/responsabilidades dispersas en el documento. Suben prompt → más costo/latencia.
    analysis_plan_top_k: int = 20            # nº de fragmentos del PLAN recuperados por agente
    analysis_normativa_top_k: int = 8        # nº de fragmentos de NORMATIVA recuperados por agente
    analysis_plan_blob_chars: int = 16000    # tope de caracteres del plan inyectados al prompt
    analysis_normativa_blob_chars: int = 4000  # tope de caracteres de normativa inyectados

    # Scraper de normativa (búsqueda en red + validación IA)
    # Obsoleto para el scraper: la colección se deriva del territorio (ej. COLOMBIA_CAUCA).
    scraper_collection_id: str = "normas_legales"
    scraper_search_max_results: int = 8
    scraper_search_query_suffix: str = "filetype:pdf"
    scraper_default_pais: str = "COLOMBIA"
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
    # SUIN-Juriscol (primera fuente de búsqueda para normas colombianas)
    scraper_suin_enabled: bool = True
    scraper_suin_base_url: str = "https://www.suin-juriscol.gov.co"
    # Búsqueda web ``{norma} suin`` (p. ej. Google/DDG) como vía principal
    scraper_suin_primary_web_search: bool = True
    # API Find de SUIN (suele fallar o devolver vacío; solo respaldo)
    scraper_suin_use_find_api: bool = False
    scraper_suin_fallback_site_search: bool = True
    scraper_suin_user: str = "web"
    scraper_suin_passwd: str = "dA4qd1uUGLLtM6IK+1xiVQ=="

    # JWT — autenticación y autorización
    jwt_secret_key: str = "cambiar-en-produccion-usar-secreto-largo-y-aleatorio"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 h

    # Usuario administrador inicial (solo si no hay usuarios en BD)
    auth_bootstrap_admin_email: str | None = None
    auth_bootstrap_admin_password: str | None = None
    auth_bootstrap_admin_nombre: str = "Administrador"
    # JSON o lista: [COLOMBIA, HUILA, PALERMO]
    auth_bootstrap_admin_territorio: str = '["COLOMBIA", "HUILA", "PALERMO"]'

    # Background scraper de normativa base
    background_scraper_duration_min: int = 30        # minutos máximos por ejecución
    background_scraper_auto_start: bool = False      # arrancar automáticamente al iniciar la app
    background_scraper_concurrency: int = 2          # normas en paralelo (menor que scraper normal)
    background_scraper_cron_hours: int = 168         # frecuencia de re-indexación periódica (0 = desactivado; 168 = semanal)

    # Análisis con scraping on-demand de normas faltantes en RAG
    analysis_scrape_missing_laws: bool = True        # activar/desactivar la búsqueda de leyes faltantes
    analysis_scrape_max_laws: int = 5                # máximo de leyes a buscar por análisis

    @property
    def mysql_url_for_migrations(self) -> str:
        """URL MySQL para Alembic; usa DEFAULT_MYSQL_URL si no hay .env."""
        explicit = (self.mysql_url or "").strip()
        return explicit or DEFAULT_MYSQL_URL

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Devuelve instancia singleton de configuración (cacheada)."""
    return Settings()
