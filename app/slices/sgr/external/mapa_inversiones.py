"""Cliente para datos públicos de proyectos SGR — datos.gov.co (Socrata) + indexación Qdrant."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── datos.gov.co Socrata API ───────────────────────────────────────────────────
# Dataset: "Proyectos de Inversión SGR" publicado por DNP/SUIFP
# El ID del dataset puede cambiar; se puede sobreescribir con la var de entorno
# DATOS_GOV_SGR_DATASET_ID en la configuración.
_DATOS_GOV_BASE = "https://www.datos.gov.co/resource"
_DATASET_PROYECTOS_SGR = "p6dx-8zbt"   # dataset SGR OCAD — verificar en datos.gov.co
_DATASET_BPIN = "xdk5-pm3f"            # BPIN DNP — verificar en datos.gov.co
_SOCRATA_TIMEOUT = 20.0

# ── Qdrant — colección de proyectos SGR indexados ─────────────────────────────
_COLECCION_SGR = "proyectos_sgr"


async def buscar_proyectos_municipio(
    *,
    divipola: str,
    sector: str | None = None,
    http: httpx.AsyncClient,
    limite: int = 30,
    dataset_id: str = _DATASET_PROYECTOS_SGR,
) -> list[dict[str, Any]]:
    """
    Consulta proyectos SGR registrados para un municipio en datos.gov.co (Socrata).

    Endpoint: GET https://www.datos.gov.co/resource/{dataset_id}.json
              ?codigomunicipio=DIVIPOLA&$limit=N[&sector=SECTOR]

    Args:
        divipola: código de 8 dígitos del municipio (DIVIPOLA)
        sector: sector SGR para filtrar resultados (opcional)
        http: cliente httpx compartido
        limite: máximo de registros a retornar
        dataset_id: ID del dataset en datos.gov.co (sobreescribible)

    Returns:
        Lista normalizada de proyectos; lista vacía si falla o no hay resultados.
    """
    # Intentamos dos variaciones del campo DIVIPOLA según el dataset
    intentos = [
        {"codigo_divipola": divipola, "$limit": limite},
        {"codigomunicipio": divipola, "$limit": limite},
        {"divipola": divipola, "$limit": limite},
    ]
    if sector:
        for p in intentos:
            p["sector"] = sector

    url = f"{_DATOS_GOV_BASE}/{dataset_id}.json"

    for params in intentos:
        try:
            resp = await http.get(url, params=params, timeout=_SOCRATA_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    logger.info(
                        "[mapa_inversiones] datos.gov.co devolvió %d proyectos para DIVIPOLA %s",
                        len(data),
                        divipola,
                    )
                    return [_normalizar_proyecto(p) for p in data if isinstance(p, dict)]
            elif resp.status_code == 404:
                logger.warning("[mapa_inversiones] Dataset %s no encontrado en datos.gov.co", dataset_id)
                break
        except httpx.TimeoutException:
            logger.warning("[mapa_inversiones] Timeout consultando datos.gov.co DIVIPOLA %s", divipola)
            break
        except Exception as exc:
            logger.warning("[mapa_inversiones] Error en datos.gov.co: %s", exc)
            break

    return []


async def buscar_por_texto_bpin(
    *,
    texto: str,
    http: httpx.AsyncClient,
    limite: int = 10,
    dataset_id: str = _DATASET_PROYECTOS_SGR,
) -> list[dict[str, Any]]:
    """
    Búsqueda de texto libre sobre el campo nombre/objeto del proyecto en datos.gov.co.
    Usa el operador $q de Socrata (full-text search).
    """
    url = f"{_DATOS_GOV_BASE}/{dataset_id}.json"
    params = {"$q": texto, "$limit": limite}
    try:
        resp = await http.get(url, params=params, timeout=_SOCRATA_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return [_normalizar_proyecto(p) for p in data if isinstance(p, dict)]
    except Exception as exc:
        logger.warning("[mapa_inversiones] buscar_por_texto_bpin falló: %s", exc)
    return []


async def indexar_en_qdrant(
    *,
    proyectos: list[dict[str, Any]],
    rag,
    divipola: str,
) -> int:
    """
    Vectoriza e indexa proyectos del DNP en la colección 'proyectos_sgr' de Qdrant
    para que el agente de duplicidad pueda hacer búsquedas semánticas locales.

    Args:
        proyectos: lista normalizada (output de buscar_proyectos_municipio)
        rag: instancia de RagService
        divipola: código del municipio (para metadatos del payload)

    Returns:
        Número de proyectos indexados exitosamente.
    """
    if not proyectos:
        return 0

    indexados = 0
    for p in proyectos:
        texto = _texto_para_vectorizar(p)
        if not texto.strip():
            continue
        try:
            await rag.ingest_text(
                text=texto,
                metadata={
                    "source": "datos_gov_co",
                    "collection": _COLECCION_SGR,
                    "nombre": p.get("nombre", ""),
                    "bpin": p.get("bpin", ""),
                    "municipio_codigo": divipola,
                    "estado": p.get("estado", ""),
                    "sector": p.get("sector", ""),
                    "fuente": p.get("fuente", "SGR"),
                },
                collection_name=_COLECCION_SGR,
            )
            indexados += 1
        except Exception as exc:
            logger.warning("[mapa_inversiones] No se pudo indexar BPIN %s: %s", p.get("bpin"), exc)

    logger.info("[mapa_inversiones] Indexados %d/%d proyectos en Qdrant colección=%s",
                indexados, len(proyectos), _COLECCION_SGR)
    return indexados


def _texto_para_vectorizar(p: dict[str, Any]) -> str:
    """Genera texto representativo del proyecto para embedding."""
    partes = [
        p.get("nombre", ""),
        p.get("sector", ""),
        p.get("objeto", ""),
        p.get("municipio", ""),
        p.get("fuente", ""),
    ]
    return " | ".join(parte for parte in partes if parte)


def _normalizar_proyecto(raw: dict[str, Any]) -> dict[str, Any]:
    """Normaliza campos del API Socrata/DNP a dict interno estándar."""
    return {
        "nombre": (
            raw.get("nombre_proyecto")
            or raw.get("nombre")
            or raw.get("objeto")
            or ""
        ),
        "bpin": raw.get("bpin") or raw.get("codigo_bpin") or raw.get("codigobpin") or None,
        "estado": (
            raw.get("estado_proyecto")
            or raw.get("estado")
            or raw.get("estadoproyecto")
            or "DESCONOCIDO"
        ).upper(),
        "sector": raw.get("sector") or raw.get("nombre_sector") or raw.get("nombresector") or "",
        "objeto": raw.get("objeto") or raw.get("descripcion") or "",
        "municipio": (
            raw.get("nombre_municipio")
            or raw.get("municipio")
            or raw.get("nombremunicipio")
            or ""
        ),
        "divipola": (
            raw.get("codigo_divipola")
            or raw.get("divipola")
            or raw.get("codigodivipola")
            or raw.get("codigomunicipio")
            or ""
        ),
        "valor_total": float(raw.get("valor_total") or raw.get("valortotal") or 0),
        "fuente": (
            raw.get("fuente_financiacion")
            or raw.get("fuente")
            or raw.get("fuentefinanciacion")
            or "SGR"
        ),
        "vigencia": raw.get("vigencia") or raw.get("anio") or raw.get("ano") or None,
    }
