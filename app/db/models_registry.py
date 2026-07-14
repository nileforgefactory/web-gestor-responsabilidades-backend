"""
Importa todos los modelos SQLAlchemy para registrar tablas en ``Base.metadata``.

Usado por Alembic (``env.py``) y por el arranque de la aplicación.
"""

from __future__ import annotations

import app.slices.alertas.models  # noqa: F401
import app.slices.auth.models  # noqa: F401
import app.slices.background_scraper.models  # noqa: F401
import app.slices.conocimiento.models  # noqa: F401
import app.slices.planes.models  # noqa: F401
import app.slices.sgr.models  # noqa: F401
