"""
Servicio de ingesta automática en background de la normativa base del sistema.

Flujo:
  1. Carga la lista de normas de normas_base.py filtradas por prioridad.
  2. Si solo_faltantes=True, descarta las que ya existen en MySQL con estado=indexado.
  3. Procesa cada norma con ScraperService (búsqueda web → validación IA → Qdrant).
  4. Se detiene cuando se acaba el tiempo (duracion_min) o se procesan todas.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings
from app.slices.background_scraper.matching import claves_posibles
from app.slices.background_scraper.normas_base import get_normas_by_priority
from app.slices.background_scraper.schemas import BackgroundScraperEstado
from app.slices.rag.service import RagService
from app.slices.scraper.service import ScraperService

logger = logging.getLogger(__name__)

# ── Estado global de la tarea (singleton por proceso) ──────────────────────
_estado: BackgroundScraperEstado = BackgroundScraperEstado(
    estado="idle",
    duracion_max_min=30,
)
_task: asyncio.Task[None] | None = None


def get_estado() -> BackgroundScraperEstado:
    return _estado


def cancel_task() -> bool:
    global _task, _estado
    if _task and not _task.done():
        _task.cancel()
        # Actualizar estado inmediatamente para que el router devuelva "cancelled"
        # sin esperar a que el CancelledError se propague dentro del task async.
        _estado.estado = "cancelled"
        _estado.norma_actual = None
        _estado.finalizado_en = datetime.now(timezone.utc)
        return True
    return False


async def _normas_ya_indexadas(settings: Settings) -> set[str]:
    """
    Consulta MySQL y arma el set de claves normalizadas de normas ya indexadas
    (por `nombre` y `archivo_nombre`), para comparar contra el catálogo sin
    depender de que el nombre de archivo coincida textualmente con el nombre
    canónico de la norma (ver `matching.claves_posibles`).
    """
    from app.core.database import mysql_available, session_scope
    from app.slices.conocimiento import repository as repo

    if not mysql_available():
        return set()

    try:
        async with session_scope() as db:
            docs = await repo.list_docs(db, estado="indexado", limit=500)
            claves: set[str] = set()
            for d in docs:
                claves |= claves_posibles(d.nombre)
                if d.archivo_nombre:
                    claves |= claves_posibles(d.archivo_nombre)
            return claves
    except Exception as exc:
        logger.warning("[BG_SCRAPER] no se pudo consultar normas indexadas: %s", exc)
        return set()


async def run_background_scraper(
    *,
    settings: Settings,
    rag: RagService,
    duracion_min: int,
    prioridad_max: int,
    pais: str,
    solo_faltantes: bool,
) -> None:
    global _estado

    normas_candidatas = get_normas_by_priority(prioridad_max)

    if solo_faltantes:
        ya_indexadas = await _normas_ya_indexadas(settings)
        normas = [
            n for n in normas_candidatas
            if not (claves_posibles(n) & ya_indexadas)
        ]
        omitidas = len(normas_candidatas) - len(normas)
        if omitidas:
            logger.info("[BG_SCRAPER] omitiendo %d normas ya indexadas", omitidas)
    else:
        normas = normas_candidatas

    _estado = BackgroundScraperEstado(
        estado="running",
        iniciado_en=datetime.now(timezone.utc),
        duracion_max_min=duracion_min,
        normas_total=len(normas),
    )

    logger.info(
        "[BG_SCRAPER] inicio: %d normas, duracion_max=%dmin, pais=%s",
        len(normas),
        duracion_min,
        pais,
    )

    deadline = asyncio.get_event_loop().time() + duracion_min * 60
    scraper = ScraperService(settings=settings, rag=rag)
    sem = asyncio.Semaphore(max(1, settings.background_scraper_concurrency))

    async def procesar(norma: str) -> dict[str, Any]:
        async with sem:
            _estado.norma_actual = norma
            try:
                resp = await scraper.buscar_normas([norma], pais=pais)
                return resp.resultados[0].model_dump() if resp.resultados else {}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[BG_SCRAPER] norma=%r error=%s", norma, exc)
                return {"estado": "error", "motivo": str(exc)}

    try:
        for norma in normas:
            # Verificar tiempo restante antes de cada norma
            if asyncio.get_event_loop().time() >= deadline:
                logger.info("[BG_SCRAPER] tiempo agotado, deteniendo")
                break

            resultado = await procesar(norma)
            estado_norma = resultado.get("estado", "error")

            _estado.normas_procesadas += 1
            if estado_norma == "indexada":
                _estado.normas_indexadas += 1
            elif estado_norma in ("error", "no_encontrada", "no_indexada"):
                _estado.normas_fallidas += 1

            logger.info(
                "[BG_SCRAPER] [%d/%d] norma=%r estado=%s",
                _estado.normas_procesadas,
                _estado.normas_total,
                norma,
                estado_norma,
            )

        _estado.estado = "completed"

    except asyncio.CancelledError:
        _estado.estado = "cancelled"
        logger.info("[BG_SCRAPER] cancelado manualmente")
    except Exception as exc:
        _estado.estado = "error"
        _estado.error = str(exc)
        logger.exception("[BG_SCRAPER] error inesperado")
    finally:
        _estado.norma_actual = None
        _estado.finalizado_en = datetime.now(timezone.utc)
        logger.info(
            "[BG_SCRAPER] fin: estado=%s indexadas=%d/%d",
            _estado.estado,
            _estado.normas_indexadas,
            _estado.normas_total,
        )


def start_background_scraper(
    *,
    settings: Settings,
    rag: RagService,
    duracion_min: int | None = None,
    prioridad_max: int = 2,
    pais: str = "COLOMBIA",
    solo_faltantes: bool = True,
) -> bool:
    """
    Lanza la tarea en background si no hay una corriendo.
    Retorna True si se inició, False si ya había una activa.
    """
    global _task, _estado

    if _task and not _task.done():
        return False

    dur = duracion_min if duracion_min is not None else settings.background_scraper_duration_min

    _task = asyncio.create_task(
        run_background_scraper(
            settings=settings,
            rag=rag,
            duracion_min=dur,
            prioridad_max=prioridad_max,
            pais=pais,
            solo_faltantes=solo_faltantes,
        )
    )
    return True
