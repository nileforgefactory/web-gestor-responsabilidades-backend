import uuid
from collections.abc import Iterable

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models


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
    ) -> int:
        points: list[models.PointStruct] = []
        for text_chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(uuid.uuid4())
            safe_title = title or document_id
            safe_src = source_filename or ""
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "chunk_id": point_id,
                        "document_id": document_id,
                        "collection_id": collection_id,
                        "text": text_chunk,
                        "title": safe_title,
                        "source_filename": safe_src,
                    },
                )
            )

        if not points:
            return 0

        await self.client.upsert(collection_name=self.collection_name, points=points, wait=True)
        return len(points)

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
