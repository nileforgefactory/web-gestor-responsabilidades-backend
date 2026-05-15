import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx
from httpx import HTTPStatusError
from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.slices.rag.chunking.strategy import chunk_document
from app.slices.rag.ollama_client import OllamaError, ollama_chat, ollama_embed
from app.slices.rag.repository import RagRepository
from app.slices.rag.schemas import (
    AgentContextResponse,
    AskResponse,
    IngestTextResponse,
    RagChunk,
    RagCitation,
    RagSearchResponse,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

_NO_EVIDENCE_ANSWER = (
    "No tengo evidencia suficiente en los documentos cargados para responder con seguridad."
)


def pseudo_embedding(text: str, vector_size: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    base_values = [byte / 255.0 for byte in digest]
    vector: list[float] = []
    while len(vector) < vector_size:
        vector.extend(base_values)
    return vector[:vector_size]


async def _with_retries(call: Callable[[], Awaitable[T]], *, attempts: int = 8) -> T:
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await call()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, OSError) as exc:
            last_exc = exc
            wait_s = min(30.0, 2.0**attempt)
            logger.warning("Reintento %s tras error de red %s", attempt + 1, exc)
            await asyncio.sleep(wait_s)
        except HTTPStatusError as exc:
            if exc.response.status_code in (408, 429, 502, 503, 504) and attempt < attempts - 1:
                last_exc = exc
                await asyncio.sleep(min(30.0, 2.0**attempt))
                continue
            raise
    assert last_exc is not None
    raise last_exc


@dataclass
class RagService:
    repository: RagRepository
    vector_size: int
    settings: Settings
    client: AsyncQdrantClient
    http: httpx.AsyncClient

    @classmethod
    def from_settings(cls, settings: Settings) -> "RagService":
        client = AsyncQdrantClient(url=settings.qdrant_url)
        repository = RagRepository(
            client=client,
            collection_name=settings.qdrant_collection,
            vector_size=settings.vector_size,
        )
        http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
        return cls(
            repository=repository,
            vector_size=settings.vector_size,
            settings=settings,
            client=client,
            http=http,
        )

    async def ensure_collection(self) -> None:
        await self.repository.ensure_collection()

    async def close(self) -> None:
        await self.client.close()
        await self.http.aclose()

    async def _embedding_for(self, text: str) -> list[float]:
        if not self.settings.use_ollama:
            return pseudo_embedding(text, self.vector_size)

        async def embed_call() -> list[float]:
            vec = await ollama_embed(
                http=self.http,
                base_url=self.settings.ollama_base_url,
                model=self.settings.ollama_embedding_model,
                prompt=text,
            )
            return vec

        try:
            return await _with_retries(embed_call)
        except OllamaError:
            raise
        except HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise RuntimeError(
                    f"Modelo de embeddings no encontrado en Ollama: "
                    f"{self.settings.ollama_embedding_model!r}. "
                    f"Ejecuta: docker compose exec ollama ollama pull "
                    f"{self.settings.ollama_embedding_model}"
                ) from exc
            raise

    async def _embedding_batch(self, texts: list[str]) -> list[list[float]]:
        semaphore = asyncio.Semaphore(max(1, self.settings.ingest_embed_concurrency))

        async def one(t: str) -> list[float]:
            async with semaphore:
                return await self._embedding_for(t)

        return await asyncio.gather(*(one(x) for x in texts))

    async def ingest_text(
        self,
        *,
        collection_id: str,
        document_id: str,
        content: str,
        chunk_size: int,
        chunk_overlap: int,
        title: str | None = None,
        source_filename: str | None = None,
        replace_existing: bool = True,
        chunk_strategy: str | None = None,
        extraction_method: str | None = None,
    ) -> IngestTextResponse:
        strat = chunk_strategy or self.settings.default_chunk_strategy
        chunking = chunk_document(
            content,
            strategy=strat,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            extraction_method=extraction_method,
        )
        chunks = chunking.chunks
        if replace_existing:
            await self.repository.delete_document_chunks(
                collection_id=collection_id, document_id=document_id
            )

        if not chunks:
            return IngestTextResponse(
                collection_id=collection_id,
                document_id=document_id,
                chunks_indexed=0,
                chunk_strategy=chunking.strategy.value,
                chunk_profile=chunking.profile.value,
                chunk_size_applied=chunking.chunk_size,
                chunk_overlap_applied=chunking.chunk_overlap,
            )

        vectors = await self._embedding_batch(chunks)
        inserted = await self.repository.upsert_chunks(
            collection_id=collection_id,
            document_id=document_id,
            chunks=chunks,
            vectors=vectors,
            title=title or document_id,
            source_filename=source_filename or "",
        )
        return IngestTextResponse(
            collection_id=collection_id,
            document_id=document_id,
            chunks_indexed=inserted,
            chunk_strategy=chunking.strategy.value,
            chunk_profile=chunking.profile.value,
            chunk_size_applied=chunking.chunk_size,
            chunk_overlap_applied=chunking.chunk_overlap,
        )

    async def search(
        self,
        *,
        query: str,
        collection_ids: list[str],
        top_k: int,
        score_threshold: float,
    ) -> RagSearchResponse:
        query_vector = await self._embedding_for(query)
        results = await self.repository.search_chunks(
            query_vector=query_vector,
            collection_ids=collection_ids,
            top_k=top_k,
            score_threshold=score_threshold,
        )

        chunks: list[RagChunk] = []
        for point in results:
            raw_score = getattr(point, "score", None)
            if raw_score is None:
                continue
            title_v = point.payload.get("title")
            src_v = point.payload.get("source_filename")
            chunks.append(
                RagChunk(
                    chunk_id=str(point.payload.get("chunk_id", "")),
                    document_id=str(point.payload.get("document_id", "")),
                    collection_id=str(point.payload.get("collection_id", "")),
                    score=float(raw_score),
                    text=str(point.payload.get("text", "")),
                    title=str(title_v) if title_v is not None else None,
                    source_filename=str(src_v) if src_v else None,
                )
            )
        return RagSearchResponse(query=query, chunks=chunks)

    async def build_agent_context(
        self, *, user_message: str, collection_ids: list[str], top_k: int
    ) -> AgentContextResponse:
        thr = float(self.settings.rag_default_score_threshold)
        search_response = await self.search(
            query=user_message,
            collection_ids=collection_ids,
            top_k=top_k,
            score_threshold=thr,
        )
        context_lines = [f"- {item.text}" for item in search_response.chunks]
        context = "\n".join(context_lines)
        citations: list[dict[str, str]] = []
        for item in search_response.chunks:
            cite: dict[str, str] = {
                "document_id": item.document_id,
                "collection_id": item.collection_id,
                "chunk_id": item.chunk_id,
            }
            if item.source_filename:
                cite["source_filename"] = str(item.source_filename)
            citations.append(cite)

        return AgentContextResponse(user_message=user_message, context=context, citations=citations)

    async def ask(
        self,
        *,
        user_message: str,
        collection_ids: list[str],
        top_k: int,
        score_threshold: float | None,
    ) -> AskResponse:
        thr = score_threshold if score_threshold is not None else float(
            self.settings.rag_default_score_threshold
        )
        retrieval = await self.search(
            query=user_message,
            collection_ids=collection_ids,
            top_k=top_k,
            score_threshold=thr,
        )

        citations = [
            RagCitation(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                collection_id=c.collection_id,
                score=c.score,
                title=c.title,
                source_filename=c.source_filename,
            )
            for c in retrieval.chunks
        ]
        used_chunks = [c.chunk_id for c in retrieval.chunks]

        if not retrieval.chunks:
            return AskResponse(
                answer=_NO_EVIDENCE_ANSWER,
                citations=[],
                confidence=0.0,
                used_chunks=[],
                retrieval_empty=True,
            )

        confidence = sum(float(c.score) for c in retrieval.chunks) / len(retrieval.chunks)

        evidence_blocks = []
        for i, c in enumerate(retrieval.chunks, start=1):
            hint = ""
            if c.title:
                hint = f" ({c.title})"
            evidence_blocks.append(
                f"[{i}] documento={c.document_id}{hint}\n{c.text}"
            )
        blob = "\n\n".join(evidence_blocks)

        if not self.settings.use_ollama:
            condensed = retrieval.chunks[0].text[:800]
            return AskResponse(
                answer=(
                    "Modo sin Ollama: fragmento recuperado más relevante:\n"
                    f"{condensed}"
                ),
                citations=citations,
                confidence=confidence,
                used_chunks=used_chunks,
                retrieval_empty=False,
            )

        system = (
            "Eres un asistente técnico. Responde en español usando "
            "exclusivamente el contexto proporcionado. "
            "No inventes información. Si el contexto no alcanza, dilo sin especular."
        )
        user = (
            f"Contexto recuperado desde documentos indexados:\n\n{blob}\n\n"
            f"Pregunta del usuario:\n{user_message}\n\n"
            "Responde de forma breve y clara citando números de bloque cuando corresponda, "
            'por ejemplo "(ver [1])".'
        )

        async def chat_call() -> str:
            return await ollama_chat(
                http=self.http,
                base_url=self.settings.ollama_base_url,
                model=self.settings.ollama_chat_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )

        try:
            answer = await _with_retries(chat_call, attempts=5)
        except HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise RuntimeError(
                    f"Modelo de chat no encontrado en Ollama: {self.settings.ollama_chat_model!r}. "
                    f"Ejecuta: docker compose exec ollama ollama pull {self.settings.ollama_chat_model}"
                ) from exc
            raise

        return AskResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            used_chunks=used_chunks,
            retrieval_empty=False,
        )
