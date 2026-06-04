import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models


@dataclass(frozen=True)
class LogicalCollectionStats:
    """Estadísticas de una colección lógica (``collection_id`` en payload)."""

    collection_id: str
    chunks: int
    documentos: int


class RagRepository:
    def __init__(self, client: AsyncQdrantClient, collection_name: str, vector_size: int) -> None:
        self.client = client
        self.collection_name = collection_name
        self.vector_size = vector_size

    async def ensure_collection(self) -> None:
        collection_exists = await self.client.collection_exists(collection_name=self.collection_name)
        if collection_exists:
            return

        await self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(size=self.vector_size, distance=models.Distance.COSINE),
        )

        await self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="collection_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    async def delete_document_chunks(self, *, collection_id: str, document_id: str) -> None:
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        ),
                        models.FieldCondition(
                            key="collection_id",
                            match=models.MatchValue(value=collection_id),
                        ),
                    ]
                ),
            ),
            wait=True,
        )

    async def upsert_chunks(
        self,
        *,
        collection_id: str,
        document_id: str,
        chunks: Iterable[str],
        vectors: Iterable[list[float]],
        title: str | None,
        source_filename: str | None,
        territorio: list[str | None] | None = None,
    ) -> int:
        points: list[models.PointStruct] = []
        for text_chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(uuid.uuid4())
            safe_title = title or document_id
            safe_src = source_filename or ""
            payload: dict = {
                "chunk_id": point_id,
                "document_id": document_id,
                "collection_id": collection_id,
                "text": text_chunk,
                "title": safe_title,
                "source_filename": safe_src,
            }
            if territorio is not None:
                payload["territorio"] = territorio
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        if not points:
            return 0

        batch_size = 64
        inserted = 0
        for start in range(0, len(points), batch_size):
            batch = points[start : start + batch_size]
            await self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
                wait=True,
            )
            inserted += len(batch)
        return inserted

    async def search_chunks(
        self,
        *,
        query_vector: list[float],
        collection_ids: list[str],
        top_k: int,
        score_threshold: float,
    ) -> list[models.ScoredPoint]:
        should_filters = [
            models.FieldCondition(key="collection_id", match=models.MatchValue(value=collection_id))
            for collection_id in collection_ids
        ]
        query_filter = models.Filter(should=should_filters)

        # qdrant-client >= 1.16 elimina `AsyncQdrantClient.search`; usar `query_points`.
        resp = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return list(resp.points)

    async def list_logical_collections(
        self,
        *,
        scroll_batch: int = 256,
        max_points: int = 50_000,
    ) -> list[LogicalCollectionStats]:
        """
        Enumera ``collection_id`` distintos en Qdrant con conteo de chunks y documentos.

        Recorre puntos por lotes (sin vectores) hasta ``max_points`` por seguridad.
        """
        chunk_counts: dict[str, int] = defaultdict(int)
        doc_ids: dict[str, set[str]] = defaultdict(set)

        offset: str | int | None = None
        scanned = 0

        while scanned < max_points:
            limit = min(scroll_batch, max_points - scanned)
            records, offset = await self.client.scroll(
                collection_name=self.collection_name,
                limit=limit,
                offset=offset,
                with_payload=["collection_id", "document_id"],
                with_vectors=False,
            )
            if not records:
                break
            for point in records:
                scanned += 1
                payload = point.payload or {}
                cid = payload.get("collection_id")
                if not cid:
                    continue
                cid_s = str(cid)
                chunk_counts[cid_s] += 1
                doc_id = payload.get("document_id")
                if doc_id:
                    doc_ids[cid_s].add(str(doc_id))
            if offset is None:
                break

        return [
            LogicalCollectionStats(
                collection_id=cid,
                chunks=chunk_counts[cid],
                documentos=len(doc_ids.get(cid, set())),
            )
            for cid in sorted(chunk_counts.keys())
        ]
