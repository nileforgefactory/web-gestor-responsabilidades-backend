"""
Carga (seed) del historial de proyectos SGR ya aprobados para verificación de
duplicidad, a partir del Excel oficial GESPROY/DNP "Balance de Seguimiento a
las Inversiones del SGR" (subido por un admin desde la UI).

Mismo patrón que app/slices/background_scraper/service.py: estado global en
memoria del proceso + asyncio.create_task + polling desde el frontend.

Filtra solo proyectos con al menos un municipio en categoría 5/6 (cruzando
contra app/slices/common/municipios_catalogo.py) e indexa el resto en Qdrant
(collection_id lógico "proyectos_sgr") para que agente_duplicidad.py pueda
buscarlos localmente en vez de depender solo de datos.gov.co en vivo.
"""

from __future__ import annotations

import asyncio
import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from sqlalchemy import delete, insert, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.slices.common.municipios_catalogo import obtener_categoria
from app.slices.rag.service import RagService
from app.slices.sgr.models import ProyectoMatrizSGR
from app.slices.sgr.schemas import DuplicidadSeedEstado

logger = logging.getLogger(__name__)

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_SHEET_PROYECTOS = "xl/worksheets/sheet2.xml"  # "PROYECTOS APROBADOS"
_HEADER_ROW = 7
_COLECCION_SGR = "proyectos_sgr"
_CONCURRENCIA = 6
_REPORTE_CADA_N_FILAS = 2000

# ── Estado global de la tarea (singleton por proceso) ──────────────────────
_estado: DuplicidadSeedEstado = DuplicidadSeedEstado(estado="idle")
_task: asyncio.Task[None] | None = None


def get_estado() -> DuplicidadSeedEstado:
    return _estado


def cancel_task() -> bool:
    global _task, _estado
    if _task and not _task.done():
        _task.cancel()
        _estado.estado = "cancelled"
        _estado.fase = None
        _estado.finalizado_en = datetime.now(timezone.utc)
        return True
    return False


def _col_letters(ref: str) -> str:
    return re.match(r"[A-Z]+", ref).group(0)


def _load_shared_strings(path: Path) -> list[str]:
    strings: list[str] = []
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag == _NS + "si":
            texts = elem.findall(f".//{_NS}t")
            strings.append("".join(t.text or "" for t in texts))
            elem.clear()
    return strings


def _parse_municipios(localizacion: str) -> list[str]:
    """'"LETICIA (AMAZ)-PUERTO NARIÑO (AMAZ)"' -> ['LETICIA', 'PUERTO NARIÑO']."""
    if not localizacion:
        return []
    nombres = []
    for tok in localizacion.split("-"):
        nombre = re.sub(r"\s*\([^)]*\)\s*$", "", tok.strip()).strip()
        if nombre:
            nombres.append(nombre)
    return nombres


def _extraer_filas(sheet_xml: Path, shared: list[str]):
    """Generador (r:int, cells:dict[str,str]) — streaming, sin cargar todo en memoria."""
    for _, elem in ET.iterparse(sheet_xml, events=("end",)):
        if elem.tag != _NS + "row":
            continue
        r = int(elem.get("r"))
        if r <= _HEADER_ROW:
            elem.clear()
            continue
        cells: dict[str, str] = {}
        for c in elem.findall(f"{_NS}c"):
            letter = _col_letters(c.get("r"))
            v = c.find(f"{_NS}v")
            if v is None or v.text is None:
                continue
            cells[letter] = shared[int(v.text)] if c.get("t") == "s" else v.text
        elem.clear()
        if cells:
            yield r, cells


def _texto_proyecto(fila: dict, municipios: list[str]) -> str:
    partes = [
        fila.get("B", ""),
        fila.get("C", ""),
        fila.get("AK", ""),
        " ".join(municipios),
        fila.get("I", ""),
    ]
    return " | ".join(p for p in partes if p)


async def run_duplicidad_seed(
    *, xlsx_path: Path, rag: RagService, delete_source_after: bool = False,
) -> None:
    global _estado

    _estado = DuplicidadSeedEstado(
        estado="running",
        fase="extrayendo",
        iniciado_en=datetime.now(timezone.utc),
    )

    tmp_dir = xlsx_path.parent / f".{xlsx_path.stem}_extract"
    try:
        tmp_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(xlsx_path) as z:
            shared_path = Path(z.extract("xl/sharedStrings.xml", tmp_dir))
            sheet_path = Path(z.extract(_SHEET_PROYECTOS, tmp_dir))

        _estado.fase = "leyendo_filas"
        shared = _load_shared_strings(shared_path)

        candidatos: list[dict] = []
        for r, fila in _extraer_filas(sheet_path, shared):
            _estado.filas_leidas += 1
            localizacion = fila.get("AM", "")
            departamento = fila.get("AK", "")
            municipios = _parse_municipios(localizacion)
            if not municipios or not departamento:
                continue

            municipios_cat_5_6 = []
            for muni in municipios:
                info = obtener_categoria(departamento, muni)
                if info and info.get("categoria") in ("5", "6"):
                    municipios_cat_5_6.append(muni)

            if not municipios_cat_5_6:
                continue

            _estado.filas_filtradas += 1
            bpin = (fila.get("A") or "").strip()
            candidatos.append({
                "bpin": bpin,
                "nombre": fila.get("B", ""),
                "sector": fila.get("C", ""),
                "estado": fila.get("I", ""),
                "valor_sgr": fila.get("U", ""),
                "departamento": departamento,
                "municipios": municipios_cat_5_6,
                "fecha_aprobacion": fila.get("AT", ""),
                "texto": _texto_proyecto(fila, municipios_cat_5_6),
            })

            if _estado.filas_leidas % _REPORTE_CADA_N_FILAS == 0:
                logger.info(
                    "[duplicidad_seed] %d filas leídas, %d filtradas",
                    _estado.filas_leidas, _estado.filas_filtradas,
                )

        logger.info(
            "[duplicidad_seed] total: %d filas, %d pasan filtro cat. 5/6",
            _estado.filas_leidas, _estado.filas_filtradas,
        )

        if not candidatos:
            _estado.estado = "completed"
            return

        _estado.fase = "indexando"
        await rag.ensure_collection()
        sem = asyncio.Semaphore(_CONCURRENCIA)
        exitosos: list[dict] = []

        async def _indexar(idx: int, c: dict) -> None:
            document_id = c["bpin"] or f"sgr-fila-{idx}"
            async with sem:
                try:
                    await rag.ingest_text(
                        collection_id=_COLECCION_SGR,
                        document_id=document_id,
                        content=c["texto"],
                        chunk_size=700,
                        chunk_overlap=100,
                        title=c["nombre"],
                        source_filename="gesproy_dnp_excel",
                        replace_existing=True,
                        extra_payload={
                            "source": "gesproy_dnp_excel",
                            "nombre": c["nombre"],
                            "bpin": c["bpin"],
                            "municipio_codigo": ",".join(c["municipios"]),
                            "departamento": c["departamento"],
                            "estado": c["estado"],
                            "sector": c["sector"],
                            "valor_sgr": c["valor_sgr"],
                            "fecha_aprobacion": c["fecha_aprobacion"],
                        },
                    )
                    _estado.proyectos_indexados += 1
                    exitosos.append({**c, "qdrant_doc_id": document_id})
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _estado.proyectos_fallidos += 1
                    logger.warning("[duplicidad_seed] error indexando BPIN=%r: %s", document_id, exc)

        await asyncio.gather(*(_indexar(i, c) for i, c in enumerate(candidatos)))

        _estado.estado = "completed"
        logger.info(
            "[duplicidad_seed] fin: %d indexados, %d fallidos de %d candidatos",
            _estado.proyectos_indexados, _estado.proyectos_fallidos, len(candidatos),
        )

        if exitosos:
            try:
                from app.core.database import mysql_available, session_scope
                if mysql_available():
                    async with session_scope() as db:
                        await _persistir_catalogo_mysql(db, exitosos)
                    logger.info("[duplicidad_seed] catálogo MySQL repoblado: %d filas", len(exitosos))
            except Exception as exc:
                logger.warning("[duplicidad_seed] no se pudo persistir el catálogo MySQL: %s", exc)

    except asyncio.CancelledError:
        _estado.estado = "cancelled"
        logger.info("[duplicidad_seed] cancelado manualmente")
    except Exception as exc:
        _estado.estado = "error"
        _estado.error = str(exc)
        logger.exception("[duplicidad_seed] error inesperado")
    finally:
        _estado.fase = None
        _estado.finalizado_en = datetime.now(timezone.utc)
        # Limpieza best-effort de archivos temporales (nunca el xlsx original
        # salvo que el llamador confirme que es un archivo temporal propio).
        try:
            if delete_source_after:
                xlsx_path.unlink(missing_ok=True)
            if tmp_dir.exists():
                for f in tmp_dir.rglob("*"):
                    if f.is_file():
                        f.unlink(missing_ok=True)
        except Exception:
            pass


def start_duplicidad_seed(
    *, xlsx_path: Path, rag: RagService, delete_source_after: bool = False,
) -> bool:
    """Lanza la tarea en background si no hay una corriendo."""
    global _task

    if _task and not _task.done():
        return False

    _task = asyncio.create_task(
        run_duplicidad_seed(xlsx_path=xlsx_path, rag=rag, delete_source_after=delete_source_after)
    )
    return True


async def _persistir_catalogo_mysql(db: AsyncSession, exitosos: list[dict]) -> None:
    """Repuebla proyectos_matriz_sgr por completo con los proyectos indexados en
    esta corrida — la tabla siempre refleja el último Excel cargado con éxito."""
    await db.execute(delete(ProyectoMatrizSGR))
    filas = [
        {
            "id": str(uuid4()),
            "bpin": c["bpin"] or None,
            "nombre": c["nombre"],
            "municipio": ",".join(c["municipios"]),
            "departamento": c["departamento"],
            "sector": c["sector"],
            "estado": c["estado"],
            "valor_sgr": c["valor_sgr"],
            "fecha_aprobacion": c["fecha_aprobacion"],
            "qdrant_doc_id": c["qdrant_doc_id"],
        }
        for c in exitosos
    ]
    for i in range(0, len(filas), 1000):
        await db.execute(insert(ProyectoMatrizSGR), filas[i : i + 1000])
    await db.commit()


async def backfill_catalogo_desde_qdrant(*, rag: RagService, db: AsyncSession) -> int:
    """Repuebla proyectos_matriz_sgr leyendo lo que ya está indexado en Qdrant —
    para proyectos indexados antes de que existiera esta tabla MySQL. Deduplica
    por document_id (un proyecto puede tener más de un chunk)."""
    payloads = await rag.repository.scroll_payloads_by_collection_id(collection_id=_COLECCION_SGR)

    vistos: dict[str, dict] = {}
    for p in payloads:
        doc_id = p.get("document_id")
        if not doc_id or doc_id in vistos:
            continue
        vistos[doc_id] = p

    await db.execute(delete(ProyectoMatrizSGR))
    filas = [
        {
            "id": str(uuid4()),
            "bpin": p.get("bpin") or None,
            "nombre": p.get("nombre") or p.get("title") or "",
            "municipio": p.get("municipio_codigo"),
            "departamento": p.get("departamento"),
            "sector": p.get("sector"),
            "estado": p.get("estado"),
            "valor_sgr": p.get("valor_sgr"),
            "fecha_aprobacion": p.get("fecha_aprobacion"),
            "qdrant_doc_id": doc_id,
        }
        for doc_id, p in vistos.items()
    ]
    for i in range(0, len(filas), 1000):
        await db.execute(insert(ProyectoMatrizSGR), filas[i : i + 1000])
    await db.commit()
    return len(filas)


async def listar_catalogo(
    db: AsyncSession, *, search: str | None = None, skip: int = 0, limit: int = 50,
) -> tuple[list[ProyectoMatrizSGR], int]:
    """Lista paginada del catálogo de proyectos de la Matriz SGR, con búsqueda
    opcional por nombre, BPIN o municipio."""
    stmt = select(ProyectoMatrizSGR)
    count_stmt = select(func.count()).select_from(ProyectoMatrizSGR)

    if search:
        like = f"%{search}%"
        condicion = or_(
            ProyectoMatrizSGR.nombre.like(like),
            ProyectoMatrizSGR.bpin.like(like),
            ProyectoMatrizSGR.municipio.like(like),
        )
        stmt = stmt.where(condicion)
        count_stmt = count_stmt.where(condicion)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(ProyectoMatrizSGR.nombre).offset(skip).limit(limit)
    filas = (await db.execute(stmt)).scalars().all()
    return list(filas), total
