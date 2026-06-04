"""Configuración centralizada de logging (niveles por módulo y librerías ruidosas)."""

from __future__ import annotations

import logging

from app.core.config import Settings

_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "asyncio",
    "multipart",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.orm",
    "ddgs",
    "duckduckgo_search",
    "primp",
    "charset_normalizer",
    "PIL",
    "pypdf",
    "pypdf._reader",
)


def _level_from_name(name: str, default: int = logging.INFO) -> int:
    return getattr(logging, name.strip().upper(), default)


def configure_logging(settings: Settings) -> None:
    """
    Aplica niveles globales y por slice.

    Variables de entorno:
    - ``APP_LOG_LEVEL``: INFO (prod), DEBUG (desarrollo)
    - ``SCRAPER_LOG_LEVEL``: opcional; por defecto igual que APP
    - ``OLLAMA_LOG_LLM_BODIES``: true para volcar prompts/respuestas completos (DEBUG)
    """
    root_level = _level_from_name(settings.app_log_level, logging.INFO)
    logging.basicConfig(
        level=root_level,
        format="%(levelname)s [%(name)s] %(message)s",
        force=True,
    )

    scraper_level = _level_from_name(
        settings.scraper_log_level or settings.app_log_level,
        root_level,
    )
    logging.getLogger("app.slices.scraper").setLevel(scraper_level)

    ollama_logger = logging.getLogger("app.slices.rag.ollama_client")
    if settings.ollama_log_llm_bodies:
        ollama_logger.setLevel(logging.DEBUG)
    else:
        ollama_logger.setLevel(max(root_level, logging.INFO))

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    if settings.sqlalchemy_log_engine:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
