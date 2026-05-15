"""Recuperación de contexto RAG para agentes."""

from __future__ import annotations

from app.slices.rag.schemas import RagChunk
from app.slices.rag.service import RagService

AGENT_QUERIES: dict[str, list[str]] = {
    "responsabilidades": [
        "responsabilidades y competencias del municipio",
        "obligaciones alcaldía secretarías plan de desarrollo",
        "metas y compromisos territoriales",
    ],
    "leyes": [
        "leyes decretos marco normativo plan desarrollo",
        "Ley 715 competencias SGP",
        "normativa vigente territorial Colombia",
    ],
    "actores": [
        "entidades actores responsables plan",
        "alcaldía gobernación ministerios",
        "instituciones participación territorial",
    ],
    "brechas": [
        "brechas vacíos responsabilidades sin asignar",
        "duplicidad competencias conflicto",
        "incumplimiento normativo obligaciones",
    ],
}


async def fetch_agent_chunks(
    rag: RagService,
    *,
    collection_ids: list[str],
    agent: str,
    extra_query: str | None = None,
    top_k: int = 5,
) -> list[RagChunk]:
    queries = list(AGENT_QUERIES.get(agent, [agent]))
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
    blocks = []
    for i, c in enumerate(chunks, start=1):
        blocks.append(f"[{i}] ({c.collection_id}/{c.document_id})\n{c.text}")
    return "\n\n".join(blocks)
