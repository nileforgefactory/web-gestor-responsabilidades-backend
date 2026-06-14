"""Esquema OpenAPI con autenticación Bearer JWT para Swagger."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

# Rutas públicas (sin JWT)
_PUBLIC_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)
_PUBLIC_EXACT_PATHS = {
    "/",
    "/api/v1/auth/login",
}


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES)


def configure_openapi_jwt(app: FastAPI) -> None:
    """Registra BearerAuth y lo aplica a rutas protegidas en Swagger."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=getattr(app, "version", "1.0.0"),
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )

        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Token obtenido en **POST /api/v1/auth/login**. "
                "Pegue solo el valor del `access_token` (sin la palabra Bearer)."
            ),
        }

        for path, path_item in schema.get("paths", {}).items():
            if _is_public_path(path):
                continue
            for method, operation in path_item.items():
                if method.startswith("x-") or not isinstance(operation, dict):
                    continue
                operation["security"] = [{"BearerAuth": []}]

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
