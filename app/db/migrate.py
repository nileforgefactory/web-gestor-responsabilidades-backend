"""Utilidades Alembic. Las migraciones se aplican manualmente (CLI), no al arrancar la API."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    return cfg


def run_migrations(*, revision: str = "head") -> None:
    """Aplica migraciones pendientes (por defecto hasta ``head``)."""
    logger.info("[DB] alembic upgrade %s", revision)
    command.upgrade(_alembic_config(), revision)
    logger.info("[DB] migraciones aplicadas (%s)", revision)


def mysql_sync_url() -> str:
    """URL síncrona para Alembic (``pymysql``) a partir de ``MYSQL_URL`` async."""
    from app.core.config import get_settings

    settings = get_settings()
    url = settings.mysql_url_for_migrations
    if url.startswith("mysql+aiomysql://"):
        return url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
    if url.startswith("mysql+asyncmy://"):
        return url.replace("mysql+asyncmy://", "mysql+pymysql://", 1)
    return url
