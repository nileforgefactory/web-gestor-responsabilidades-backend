"""Constantes y utilidades OpenAPI para documentación Swagger (español)."""

from __future__ import annotations

from typing import Any

# Respuestas HTTP comunes reutilizables en decoradores de rutas.
RESPUESTAS_ESTANDAR: dict[int | str, dict[str, Any]] = {
    400: {"description": "Solicitud inválida (archivo vacío, formato no soportado, etc.)."},
    422: {"description": "Error de validación de parámetros o cuerpo JSON."},
    500: {"description": "Error interno no controlado."},
    503: {"description": "Dependencia no disponible (MySQL, Ollama o Qdrant)."},
}

RESPUESTAS_RAG: dict[int | str, dict[str, Any]] = {
    **RESPUESTAS_ESTANDAR,
    502: {"description": "Fallo de comunicación con Qdrant u Ollama."},
    504: {"description": "Tiempo de espera agotado al invocar Ollama (generación o embeddings)."},
}

RESPUESTAS_ANALISIS: dict[int | str, dict[str, Any]] = {
    **RESPUESTAS_RAG,
    200: {
        "description": "Análisis completado (JSON) o flujo SSE iniciado (stream=true).",
    },
}

RESPUESTAS_MYSQL: dict[int | str, dict[str, Any]] = {
    **RESPUESTAS_ESTANDAR,
    401: {"description": "Token JWT ausente, inválido o expirado."},
    403: {"description": "Permiso denegado (rol o territorio)."},
    404: {"description": "Recurso no encontrado en base de datos."},
}
