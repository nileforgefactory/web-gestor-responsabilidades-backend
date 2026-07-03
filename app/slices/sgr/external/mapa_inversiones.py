"""Cliente para el Mapa de Inversiones del DNP — consulta pública de proyectos SGR."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# URL pública del API del Mapa de Inversiones DNP
_BASE_URL = "https://mapadeinversiones.dnp.gov.co/api"

# Timeout conservador — API gubernamental puede ser lenta
_TIMEOUT = 15.0


async def buscar_proyectos_municipio(
    *,
    divipola: str,
    sector: str | None = None,
    http: httpx.AsyncClient,
    limite: int = 20,
) -> list[dict[str, Any]]:
    """
    Busca proyectos SGR registrados para un municipio en el Mapa de Inversiones DNP.

    Args:
        divipola: código de 8 dígitos del municipio
        sector: sector SGR opcional para filtrar (ej. "Agua potable y saneamiento")
        http: cliente httpx compartido
        limite: máximo de resultados

    Returns:
        Lista de proyectos con {nombre, bpin, estado, sector, municipio, valor, fuente}
    """
    params: dict[str, Any] = {
        "codigoDivipola": divipola,
        "limite": limite,
    }
    if sector:
        params["sector"] = sector

    try:
        response = await http.get(
            f"{_BASE_URL}/proyectos",
            params=params,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        proyectos = data.get("proyectos") or data.get("data") or []
        return [_normalizar_proyecto(p) for p in proyectos if isinstance(p, dict)]
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "[mapa_inversiones] HTTP %s al consultar DIVIPOLA %s: %s",
            exc.response.status_code,
            divipola,
            exc,
        )
        return []
    except Exception as exc:
        logger.warning("[mapa_inversiones] Error consultando DIVIPOLA %s: %s", divipola, exc)
        return []


def _normalizar_proyecto(raw: dict[str, Any]) -> dict[str, Any]:
    """Normaliza los campos del API DNP a un dict estándar interno."""
    return {
        "nombre": raw.get("nombre") or raw.get("nombreProyecto") or "",
        "bpin": raw.get("bpin") or raw.get("codigoBpin") or None,
        "estado": raw.get("estado") or raw.get("estadoProyecto") or "DESCONOCIDO",
        "sector": raw.get("sector") or raw.get("nombreSector") or "",
        "municipio": raw.get("municipio") or raw.get("nombreMunicipio") or "",
        "divipola": raw.get("divipola") or raw.get("codigoDivipola") or "",
        "valor_total": raw.get("valorTotal") or raw.get("valor") or 0,
        "fuente": raw.get("fuenteFinanciacion") or raw.get("fuente") or "SGR",
        "vigencia": raw.get("vigencia") or raw.get("anio") or None,
    }
