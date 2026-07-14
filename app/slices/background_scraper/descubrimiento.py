"""Descubrimiento de normas relevantes con IA.

Antes de scrapear, la IA propone la lista de normas (nacionales, departamentales
y municipales) relevantes para SGR/regalías y el plan de desarrollo del territorio.
Las nuevas se registran en `normas_territoriales`; luego el indexer las trae y el
scraper valida cada una con IA (si la IA inventó un número, no se indexa).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.slices.background_scraper import territorial
from app.slices.background_scraper.matching import claves_posibles
from app.slices.background_scraper.normas_base import NORMAS_BASE
from app.slices.background_scraper.self_heal import detectar_normas
from app.slices.rag.ai_client import ai_chat
from app.slices.scraper.web_search import build_web_search_provider

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Eres un experto en normativa colombiana de finanzas públicas territoriales, "
    "Sistema General de Regalías (SGR) y planes de desarrollo. Investiga de forma "
    "EXHAUSTIVA y lista TODAS las normas REALMENTE EXISTENTES y relevantes de todos "
    "estos tipos cuando apliquen:\n"
    "- Leyes y Decretos (leyes orgánicas, reglamentarios, únicos)\n"
    "- Resoluciones, Circulares y Directivas (ej. de DNP, MinHacienda, DAFP)\n"
    "- Documentos CONPES (ej. 'CONPES 4023 de 2021' o 'CONPES 3918')\n"
    "- Ordenanzas departamentales y Acuerdos municipales\n"
    "IMPORTANTE — cadena normativa: incluye también las normas que MODIFICAN, "
    "REGLAMENTAN, ADICIONAN o DEROGAN a las anteriores (ej. si una ley fue "
    "modificada o derogada, incluye tanto la original como la que la modifica/deroga), "
    "para tener el marco vigente completo.\n"
    "Responde SOLO con los códigos, uno por línea, sin explicaciones ni viñetas. "
    "Usa el formato 'Tipo N de AAAA' (para CONPES: 'CONPES N de AAAA'). "
    "No inventes números; si no estás seguro de una norma, no la incluyas."
)


def _contexto_territorio(municipio: str | None, departamento: str | None) -> str:
    partes = []
    if municipio:
        partes.append(f"municipio de {municipio}")
    if departamento:
        partes.append(f"departamento de {departamento}")
    return " del " + ", ".join(partes) if partes else " de Colombia"


async def descubrir_normas(
    *,
    http,
    settings: Settings,
    municipio: str | None = None,
    departamento: str | None = None,
    tema: str = "Sistema General de Regalías (SGR) y planes de desarrollo",
) -> list[str]:
    """Pide a la IA los códigos de normas relevantes y los extrae (sin duplicados)."""
    territorio = _contexto_territorio(municipio, departamento)
    user = (
        f"Investiga y lista TODAS las normas colombianas relevantes para {tema}{territorio}. "
        "Incluye leyes, decretos, resoluciones, circulares, directivas, Documentos CONPES, "
        "ordenanzas departamentales y acuerdos municipales, ADEMÁS de las normas que las "
        "modifican, reglamentan o derogan (cadena normativa completa y vigente). "
        "Sé exhaustivo con el marco de regalías (SGR), presupuesto y planeación. "
        "Devuelve solo los códigos, uno por línea."
    )
    try:
        raw = await ai_chat(
            http=http,
            settings=settings,
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        )
    except Exception as exc:
        logger.warning("[descubrimiento] la IA no respondió: %s", exc)
        return []
    return detectar_normas(raw or "")


async def descubrir_normas_web(
    *,
    http,
    settings: Settings,
    municipio: str | None = None,
    departamento: str | None = None,
) -> list[str]:
    """Consulta internet (buscador del scraper) y extrae códigos de norma de los
    títulos/snippets de los resultados. Complementa al LLM con fuentes reales."""
    try:
        provider = build_web_search_provider(http=http, settings=settings)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("[descubrimiento] no se pudo construir el buscador web: %s", exc)
        return []

    ctx = (municipio or departamento or "Colombia").strip()
    consultas = [
        f"normas Sistema General de Regalías SGR ley decreto {ctx}",
        f"documento CONPES regalías inversión pública {ctx}",
        f"marco normativo plan de desarrollo leyes decretos resoluciones {ctx}",
        f"derogatoria modificación ley regalías SGR Colombia",
    ]
    max_results = getattr(settings, "scraper_search_max_results", 8) or 8

    codigos: list[str] = []
    for q in consultas:
        try:
            hits = await provider.search(q, max_results=max_results)
        except Exception as exc:
            logger.warning("[descubrimiento] búsqueda web falló (%r): %s", q, exc)
            continue
        for h in hits:
            texto = f"{h.title or ''} {h.snippet or ''} {h.url or ''}"
            for c in detectar_normas(texto):
                if c not in codigos:
                    codigos.append(c)
    logger.info("[descubrimiento] web: %d códigos extraídos de internet", len(codigos))
    return codigos


async def descubrir_y_registrar(
    db: AsyncSession,
    *,
    http,
    settings: Settings,
    municipio: str | None = None,
    departamento: str | None = None,
    tema: str = "Sistema General de Regalías (SGR) y planes de desarrollo",
    usar_web: bool = True,
    limite: int = 80,
) -> dict:
    """Descubre normas (LLM + internet) y registra las nuevas en `normas_territoriales`."""
    llm_codes = await descubrir_normas(
        http=http, settings=settings, municipio=municipio, departamento=departamento, tema=tema
    )
    web_codes = (
        await descubrir_normas_web(
            http=http, settings=settings, municipio=municipio, departamento=departamento
        )
        if usar_web
        else []
    )

    # Unión preservando orden: primero LLM (más contextual), luego web.
    descubiertas: list[str] = []
    for c in llm_codes + web_codes:
        if c not in descubiertas:
            descubiertas.append(c)
    descubiertas = descubiertas[:limite]

    # Claves ya cubiertas: nacionales del catálogo base + territoriales existentes.
    claves_cubiertas: set[str] = set()
    for cod, _pri in NORMAS_BASE:
        claves_cubiertas |= claves_posibles(cod)
    existentes = await territorial.listar(db)
    for n in existentes:
        claves_cubiertas |= claves_posibles(n.codigo)

    etiqueta = (municipio or departamento or "").strip() or None
    agregadas: list[str] = []
    ya_presentes: list[str] = []
    for codigo in descubiertas:
        if claves_posibles(codigo) & claves_cubiertas:
            ya_presentes.append(codigo)
            continue
        await territorial.crear(
            db,
            codigo=codigo,
            territorio=etiqueta,
            prioridad=2,
            descripcion="Descubierta por IA",
        )
        agregadas.append(codigo)
        claves_cubiertas |= claves_posibles(codigo)

    logger.info(
        "[descubrimiento] descubiertas=%d agregadas=%d ya_presentes=%d",
        len(descubiertas),
        len(agregadas),
        len(ya_presentes),
    )
    return {
        "descubiertas": descubiertas,
        "agregadas": agregadas,
        "ya_presentes": ya_presentes,
    }
