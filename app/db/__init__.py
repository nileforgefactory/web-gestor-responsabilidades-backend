"""Utilidades de base de datos (registro de modelos y migraciones Alembic)."""

from app.db.migrate import run_migrations

__all__ = ["run_migrations"]
