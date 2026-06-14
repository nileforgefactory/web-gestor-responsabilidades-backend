"""Recuperación de contexto RAG para agentes con distinción territorial."""

from __future__ import annotations

from app.slices.rag.schemas import RagChunk
from app.slices.rag.service import RagService

# Queries base por agente
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

# Queries adicionales según nivel territorial (refinan la búsqueda)
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


async def fetch_agent_chunks(
    rag: RagService,
    *,
    collection_ids: list[str],
    agent: str,
    extra_query: str | None = None,
    top_k: int = 5,
    nivel: str = "municipal",
) -> list[RagChunk]:
    """
    Ejecuta búsquedas RAG por agente combinando queries base + queries del nivel territorial.

    Deduplica chunks por ``chunk_id`` y re-rankea por score máximo.
    """
    queries = list(AGENT_QUERIES.get(agent, [agent]))

    # Agrega queries específicas del nivel territorial (recomendación distinción por nivel)
    nivel_extra = NIVEL_QUERIES.get(nivel, {}).get(agent, [])
    queries = nivel_extra + queries  # nivel va primero para mayor peso

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
