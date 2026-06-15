"""Recuperación de contexto RAG para agentes con distinción territorial."""

from __future__ import annotations

import re

from app.slices.rag.schemas import RagChunk
from app.slices.rag.service import RagService

# Queries base por agente (normativa)
AGENT_QUERIES: dict[str, list[str]] = {
    "responsabilidades": [
        "responsabilidades y competencias territoriales",
        "obligaciones secretarías entidades plan de desarrollo",
        "metas compromisos competencias territoriales",
    ],
    "leyes": [
        "leyes decretos marco normativo plan desarrollo territorial",
        "Ley 715 SGP competencias territoriales Colombia",
        "normativa vigente territorial Colombia decreto ley política",
    ],
    "actores": [
        "entidades actores institucionales responsables plan",
        "alcaldía gobernación ministerios secretarías",
        "instituciones participación territorial Colombia",
    ],
    "brechas": [
        "brechas vacíos responsabilidades sin asignar territoriales",
        "duplicidad competencias conflicto normativo territorial",
        "incumplimiento normativo obligaciones sin responsable",
        "competencias obligatorias ley sin actor asignado",
    ],
}

# Queries adicionales según nivel territorial
NIVEL_QUERIES: dict[str, dict[str, list[str]]] = {
    "municipal": {
        "responsabilidades": [
            "competencias municipio Ley 136 Ley 715 servicios públicos",
            "obligaciones alcaldía gobierno local servicios básicos",
        ],
        "leyes": [
            "Ley 136 de 1994 régimen municipal competencias",
            "Ley 152 de 1994 planes de desarrollo municipal",
            "Ley 715 de 2001 sistema general de participaciones municipio",
        ],
        "brechas": [
            "brechas municipio obligaciones Ley 715 servicios básicos sin responsable",
        ],
    },
    "departamental": {
        "responsabilidades": [
            "competencias departamento gobernación LOOT coordinación",
            "obligaciones gobernación secretarías departamentales SGP",
        ],
        "leyes": [
            "LOOT Ley 1454 ordenamiento territorial departamental",
            "Ley 715 competencias departamento SGP educación salud",
        ],
        "brechas": [
            "brechas departamento gobernación coordinación municipios vacíos",
        ],
    },
    "nacional": {
        "responsabilidades": [
            "competencias nacionales ministerios política pública",
            "obligaciones estado colombiano constitución derechos fundamentales",
        ],
        "leyes": [
            "Constitución Política 1991 derechos organización del estado",
            "plan nacional de desarrollo gobierno competencias nacionales",
        ],
        "brechas": [
            "brechas nación coordinación territorial competencias sin ejecutar",
        ],
    },
}

# Palabras clave por agente para extraer frases relevantes del texto del plan
_PLAN_KEYWORDS: dict[str, list[str]] = {
    "responsabilidades": [
        "responsable", "responsabilidad", "competencia", "encargado",
        "deberá", "obligación", "implementar", "ejecutar", "coordinar",
        "garantizar", "asegurar", "liderar", "gestionar",
    ],
    "leyes": [
        "ley ", "decreto", "resolución", "artículo", "normativa",
        "norma", "marco legal", "código", "acuerdo", "ordenanza",
        "constitución", "reglamento",
    ],
    "actores": [
        "alcaldía", "secretaría", "ministerio", "gobernación", "entidad",
        "institución", "organismo", "dependencia", "despacho", "oficina",
        "departamento administrativo", "consejo",
    ],
    "brechas": [
        "sin responsable", "no se define", "ausente", "vacío",
        "no asignado", "indefinido", "no se establece", "falta de",
        "carencia", "deficiencia", "no cuenta con",
    ],
}


def extract_plan_queries(plan_text: str, agent: str, max_queries: int = 5) -> list[str]:
    """
    Extrae oraciones del plan que contienen palabras clave del agente.
    Estas se usan como queries RAG dinámicas para recuperar chunks relevantes.
    """
    keywords = _PLAN_KEYWORDS.get(agent, [])
    if not keywords or not plan_text:
        return []

    sentences = re.split(r"[.;\n]\s*", plan_text)
    relevant: list[str] = []
    seen: set[str] = set()

    for s in sentences:
        s = s.strip()
        if len(s) < 40 or len(s) > 400:
            continue
        s_lower = s.lower()
        if not any(kw in s_lower for kw in keywords):
            continue
        key = s_lower[:60]
        if key in seen:
            continue
        seen.add(key)
        relevant.append(s)
        if len(relevant) >= max_queries:
            break

    return relevant


async def fetch_plan_chunks(
    rag: RagService,
    *,
    plan_collection_id: str,
    doc_id: str,
    agent: str,
    plan_text: str,
    top_k: int = 8,
    nivel: str = "municipal",
) -> list[RagChunk]:
    """
    Recupera los chunks MÁS RELEVANTES del plan indexado en Qdrant para el agente.
    Combina queries dinámicas (extraídas del texto) + queries base del agente.
    Filtra por document_id para no mezclar con otros planes.
    """
    # Queries dinámicas del texto del plan + queries fijas del nivel
    dynamic = extract_plan_queries(plan_text, agent, max_queries=3)
    base    = NIVEL_QUERIES.get(nivel, {}).get(agent, [])[:2] + AGENT_QUERIES.get(agent, [])[:2]
    queries = (dynamic + base)[:5]  # máx 5 queries para no saturar

    seen: dict[str, RagChunk] = {}
    for q in queries:
        res = await rag.search(
            query=q,
            collection_ids=[plan_collection_id],
            top_k=top_k,
            score_threshold=0.15,  # umbral bajo: queremos todo lo relevante del plan
            document_id=doc_id,
        )
        for ch in res.chunks:
            if ch.chunk_id not in seen or ch.score > seen[ch.chunk_id].score:
                seen[ch.chunk_id] = ch

    ranked = sorted(seen.values(), key=lambda c: c.score, reverse=True)
    return ranked[:top_k]


async def fetch_normativa_chunks(
    rag: RagService,
    *,
    normativa_collection_ids: list[str],
    agent: str,
    extra_query: str | None = None,
    top_k: int = 8,
    nivel: str = "municipal",
) -> list[RagChunk]:
    """
    Recupera chunks de la base de conocimiento normativa (leyes, decretos, etc.)
    usando queries fijas por agente + nivel + query extra del coordinador.
    """
    nivel_extra = NIVEL_QUERIES.get(nivel, {}).get(agent, [])
    base        = AGENT_QUERIES.get(agent, [agent])
    queries     = list(nivel_extra) + list(base)
    if extra_query:
        queries.insert(0, extra_query)

    seen: dict[str, RagChunk] = {}
    for q in queries:
        res = await rag.search(
            query=q,
            collection_ids=normativa_collection_ids,
            top_k=top_k,
            score_threshold=float(rag.settings.rag_default_score_threshold),
        )
        for ch in res.chunks:
            if ch.chunk_id not in seen or ch.score > seen[ch.chunk_id].score:
                seen[ch.chunk_id] = ch

    ranked = sorted(seen.values(), key=lambda c: c.score, reverse=True)
    return ranked[: top_k * 2]


# Mantener compatibilidad con código existente
async def fetch_agent_chunks(
    rag: RagService,
    *,
    collection_ids: list[str],
    agent: str,
    extra_query: str | None = None,
    top_k: int = 5,
    nivel: str = "municipal",
) -> list[RagChunk]:
    """Búsqueda RAG combinada (plan + normativa) — compatibilidad con scraper/coordinador."""
    queries = list(NIVEL_QUERIES.get(nivel, {}).get(agent, [])) + list(AGENT_QUERIES.get(agent, [agent]))
    if extra_query:
        queries.insert(0, extra_query)

    seen: dict[str, RagChunk] = {}
    for q in queries:
        res = await rag.search(
            query=q,
            collection_ids=collection_ids,
            top_k=top_k,
            score_threshold=float(rag.settings.rag_default_score_threshold),
        )
        for ch in res.chunks:
            if ch.chunk_id not in seen or ch.score > seen[ch.chunk_id].score:
                seen[ch.chunk_id] = ch

    ranked = sorted(seen.values(), key=lambda c: c.score, reverse=True)
    return ranked[: top_k * 2]


def chunks_to_context_blob(chunks: list[RagChunk]) -> str:
    """Formatea chunks numerados para inyectar en el prompt del LLM."""
    blocks = []
    for i, c in enumerate(chunks, start=1):
        blocks.append(f"[{i}] ({c.collection_id}/{c.document_id})\n{c.text}")
    return "\n\n".join(blocks)
