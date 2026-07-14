"""Búsqueda en línea de departamento/municipio/DIVIPOLA — datos.gov.co (Socrata).

Dataset: "DIVIPOLA - Códigos municipios", publicado por MinTIC (1122 filas,
confirmado en vivo durante el desarrollo). La categoría municipal
(Ley 617/2000) NO viene en este dataset — se cruza aparte contra el catálogo
embebido de `municipios_catalogo.py`.

El filtro `$q` de Socrata es sensible a tildes (ej. "OICATA" no encuentra
"OICATÁ"), muy común al escribir sin acentos. Como el dataset completo es
pequeño, se trae entero una vez (consulta en línea real) y el filtrado por
texto se hace localmente sin distinguir mayúsculas/tildes.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from typing import Any

import httpx

from app.slices.common.municipios_catalogo import obtener_categoria

logger = logging.getLogger(__name__)

_DATOS_GOV_BASE = "https://www.datos.gov.co/resource"
_DATASET_DIVIPOLA = "gdxc-w37w"
_SOCRATA_TIMEOUT = 15.0
_TOTAL_MUNICIPIOS = 1200  # el dataset real tiene 1122 filas; margen por si crece

_cache: list[dict[str, Any]] | None = None
_cache_lock = asyncio.Lock()


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _fold(text: str) -> str:
    return _strip_accents(text).upper()


async def _cargar_todos(http: httpx.AsyncClient) -> list[dict[str, Any]]:
    global _cache
    if _cache is not None:
        return _cache

    async with _cache_lock:
        if _cache is not None:
            return _cache

        url = f"{_DATOS_GOV_BASE}/{_DATASET_DIVIPOLA}.json"
        try:
            resp = await http.get(url, params={"$limit": _TOTAL_MUNICIPIOS}, timeout=_SOCRATA_TIMEOUT)
        except httpx.TimeoutException:
            logger.warning("[divipola_search] Timeout cargando dataset DIVIPOLA completo")
            return []
        except Exception as exc:
            logger.warning("[divipola_search] Error cargando dataset DIVIPOLA: %s", exc)
            return []

        if resp.status_code != 200:
            logger.warning("[divipola_search] datos.gov.co devolvió status=%s al cargar DIVIPOLA", resp.status_code)
            return []

        data = resp.json()
        if not isinstance(data, list):
            return []

        _cache = [row for row in data if isinstance(row, dict) and row.get("dpto") and row.get("nom_mpio")]
        logger.info("[divipola_search] Dataset DIVIPOLA cacheado: %d municipios", len(_cache))
        return _cache


async def listar_departamentos(http: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Agrupa el dataset DIVIPOLA por departamento con sus municipios.

    Pensado para poblar dos selectores dependientes (departamento -> municipios)
    al crear un usuario. Cada municipio incluye su código DIVIPOLA y la categoría
    municipal (Ley 617/2000) si está en el catálogo embebido.

    Returns:
        `[{"departamento", "municipios": [{"municipio","divipola","categoria"}]}]`
        ordenado alfabéticamente; lista vacía si falla la consulta.
    """
    todos = await _cargar_todos(http)
    if not todos:
        return []

    grupos: dict[str, list[dict[str, Any]]] = {}
    for row in todos:
        departamento = row.get("dpto", "")
        municipio = row.get("nom_mpio", "")
        if not departamento or not municipio:
            continue
        info = obtener_categoria(departamento, municipio)
        grupos.setdefault(departamento, []).append({
            "municipio": municipio,
            "divipola": row.get("cod_mpio") or row.get("cod_dpto") or "",
            "categoria": (info or {}).get("categoria"),
        })

    salida = [
        {
            "departamento": departamento,
            "municipios": sorted(municipios, key=lambda m: m["municipio"]),
        }
        for departamento, municipios in grupos.items()
    ]
    salida.sort(key=lambda d: d["departamento"])
    return salida


async def buscar_municipios(
    q: str,
    *,
    http: httpx.AsyncClient,
    limite: int = 15,
) -> list[dict[str, Any]]:
    """
    Busca municipios por texto libre (nombre de municipio o departamento),
    sin distinguir mayúsculas/tildes, y enriquece cada resultado con la
    categoría municipal (Ley 617/2000) si está en el catálogo embebido.

    Returns:
        Lista de `{"departamento", "municipio", "divipola", "categoria"}`;
        lista vacía si falla la consulta o no hay resultados.
    """
    q = q.strip()
    if len(q) < 2:
        return []

    todos = await _cargar_todos(http)
    if not todos:
        return []

    q_fold = _fold(q)
    resultados: list[dict[str, Any]] = []
    for row in todos:
        departamento = row.get("dpto", "")
        municipio = row.get("nom_mpio", "")
        if q_fold not in _fold(municipio) and q_fold not in _fold(departamento):
            continue

        info = obtener_categoria(departamento, municipio)
        resultados.append({
            "departamento": departamento,
            "municipio": municipio,
            "divipola": row.get("cod_mpio") or row.get("cod_dpto") or "",
            "categoria": (info or {}).get("categoria"),
        })
        if len(resultados) >= limite:
            break

    return resultados
