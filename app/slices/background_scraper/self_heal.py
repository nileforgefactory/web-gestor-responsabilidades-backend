"""Auto-sanado del RAG: detecta normas citadas en un texto y, si no están
indexadas, las trae del scraper (web → descarga → validación IA → Qdrant) antes
de que el agente continúe.

Se usa de forma **síncrona** en los flujos SGR (evaluar proyecto, generar/editar
Ficha MGA) y en el análisis de planes: el análisis se "detiene", indexa la norma
faltante y "reanuda" ya con ella disponible.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.core.config import Settings
from app.slices.background_scraper.matching import claves_posibles
from app.slices.background_scraper.service import _normas_ya_indexadas
from app.slices.scraper.service import ScraperService

logger = logging.getLogger(__name__)

# Detecta referencias a normas con formato "Tipo N de AAAA":
# nacionales (Ley/Decreto/Resolución/Directiva/Circular) y territoriales
# (Acuerdo municipal, Ordenanza departamental).
_NORMA_RE = re.compile(
    r"\b(ley|decreto|resoluci[oó]n|acuerdo|ordenanza|circular|directiva)\s*"
    r"(?:n[°º.]?\s*)?(\d{1,4})\s*(?:de|del|/|-|\s)\s*((?:19|20)\d{2})\b",
    re.IGNORECASE,
)

# CONPES tiene formato propio: "CONPES 3918" o "Documento CONPES 4023 de 2021"
# (el año es opcional; el número identifica el documento).
_CONPES_RE = re.compile(
    r"\b(?:documento\s+)?conpes\s*(?:n[°º.]?\s*)?(\d{3,4})(?:\s*(?:de|del)?\s*((?:19|20)\d{2}))?\b",
    re.IGNORECASE,
)

_TIPO_CANON = {
    "ley": "Ley",
    "decreto": "Decreto",
    "resolucion": "Resolución",
    "resolución": "Resolución",
    "acuerdo": "Acuerdo",
    "ordenanza": "Ordenanza",
    "circular": "Circular",
    "directiva": "Directiva",
}

# Cota de seguridad: nº máximo de normas que se traen en una sola pasada
# (evita que un texto con muchas citas dispare decenas de descargas).
_LIMITE_POR_DEFECTO = 6

# Callback de streaming: (fase, norma) -> None  (fase: "indexando"|"indexada"|"fallida")
EventoCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class AutoSanadoResultado:
    detectadas: list[str] = field(default_factory=list)
    ya_presentes: list[str] = field(default_factory=list)
    agregadas: list[str] = field(default_factory=list)
    fallidas: list[str] = field(default_factory=list)

    @property
    def hubo_cambios(self) -> bool:
        return bool(self.agregadas)


def detectar_normas(texto: str) -> list[str]:
    """Extrae referencias canónicas de normas de un texto libre (sin duplicados)."""
    if not texto:
        return []
    vistas: dict[str, str] = {}
    for m in _NORMA_RE.finditer(texto):
        tipo_raw, numero, anio = m.group(1), m.group(2), m.group(3)
        tipo = _TIPO_CANON.get(tipo_raw.lower(), tipo_raw.capitalize())
        canon = f"{tipo} {int(numero)} de {anio}"
        vistas.setdefault(canon.lower(), canon)
    # CONPES (formato aparte, año opcional)
    for m in _CONPES_RE.finditer(texto):
        numero, anio = m.group(1), m.group(2)
        canon = f"CONPES {int(numero)}" + (f" de {anio}" if anio else "")
        vistas.setdefault(canon.lower(), canon)
    return list(vistas.values())


async def asegurar_normas_en_rag(
    textos: list[str],
    *,
    rag,
    settings: Settings,
    pais: str = "COLOMBIA",
    limite: int = _LIMITE_POR_DEFECTO,
    on_evento: EventoCallback | None = None,
    timeout_por_norma: float = 90.0,
) -> AutoSanadoResultado:
    """Detecta normas citadas en `textos` y trae al RAG las que falten.

    Args:
        textos: fragmentos de texto donde buscar referencias a normas.
        rag: RagService (para indexar en Qdrant vía ScraperService).
        on_evento: callback opcional para emitir progreso (streaming SSE).
    """
    detectadas: list[str] = []
    for t in textos:
        for n in detectar_normas(t or ""):
            if n not in detectadas:
                detectadas.append(n)

    resultado = AutoSanadoResultado(detectadas=detectadas)
    if not detectadas:
        return resultado

    try:
        ya = await _normas_ya_indexadas(settings)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("[self_heal] no se pudo consultar normas indexadas: %s", exc)
        ya = set()

    faltantes: list[str] = []
    for n in detectadas:
        if claves_posibles(n) & ya:
            resultado.ya_presentes.append(n)
        else:
            faltantes.append(n)

    faltantes = faltantes[:limite]
    if not faltantes:
        return resultado

    scraper = ScraperService(settings=settings, rag=rag)
    for norma in faltantes:
        logger.info("[self_heal] norma faltante detectada, indexando: %r", norma)
        if on_evento:
            await on_evento("indexando", norma)
        try:
            resp = await asyncio.wait_for(
                scraper.buscar_normas([norma], pais=pais), timeout=timeout_por_norma
            )
            estado = resp.resultados[0].estado if resp.resultados else "no_indexada"
            if estado == "indexada":
                resultado.agregadas.append(norma)
                if on_evento:
                    await on_evento("indexada", norma)
            else:
                resultado.fallidas.append(norma)
                if on_evento:
                    await on_evento("fallida", norma)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("[self_heal] no se pudo indexar %r: %s", norma, exc)
            resultado.fallidas.append(norma)
            if on_evento:
                await on_evento("fallida", norma)

    logger.info(
        "[self_heal] detectadas=%d ya=%d agregadas=%d fallidas=%d",
        len(resultado.detectadas),
        len(resultado.ya_presentes),
        len(resultado.agregadas),
        len(resultado.fallidas),
    )
    return resultado
