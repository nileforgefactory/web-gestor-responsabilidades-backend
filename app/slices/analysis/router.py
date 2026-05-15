"""Endpoints HTTP para el slice de análisis agentico."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.session_store import get_session_store
from app.dependencies import get_rag_service
from app.slices.analysis.schemas import AnalysisStartResponse, AnalyzePlanRequest
from app.slices.analysis.service import analyze_plan_stream
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post(
    "/analyze-plan/stream",
    summary="Analizar plan con loop agentico (SSE)",
    description=(
        "Inicia el análisis agentico de un plan de desarrollo. "
        "Responde con un stream SSE de eventos. "
        "Cada evento tiene `type`: log | agent_start | agent_done | coordinator_decision | saving | done | error | heartbeat."
    ),
)
async def analyze_plan(
    request: AnalyzePlanRequest,
    rag: RagService = Depends(get_rag_service),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    generator, session_id = await analyze_plan_stream(request, rag, db)
    headers = {}
    if session_id:
        headers["X-Session-Id"] = session_id
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            **headers,
        },
    )


@router.get(
    "/session/{session_id}/replay",
    summary="Reconectar a sesión de análisis (SSE replay)",
    description=(
        "Permite reconectar a un análisis en curso o ver los eventos pasados. "
        "Primero emite todos los eventos históricos almacenados, "
        "luego suscribe a nuevos eventos vía Redis Pub/Sub. "
        "Requiere Redis configurado (REDIS_URL)."
    ),
)
async def replay_session(session_id: str) -> StreamingResponse:
    store = get_session_store()
    if not store:
        raise HTTPException(
            status_code=503,
            detail="Replay no disponible: Redis no está configurado (REDIS_URL).",
        )

    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada.")

    async def generate():
        # Replay de eventos históricos
        for event in session.get("events", []):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        if session.get("status") == "done":
            yield 'data: {"type":"done","msg":"replay_complete"}\n\n'
            return

        # Suscribirse a nuevos eventos via Pub/Sub
        pubsub = store.redis.pubsub()
        await pubsub.subscribe(f"analysis_channel:{session_id}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    yield f"data: {data}\n\n"
                    try:
                        parsed = json.loads(data)
                        if parsed.get("type") in ("done", "error"):
                            break
                    except json.JSONDecodeError:
                        pass
        finally:
            await pubsub.unsubscribe(f"analysis_channel:{session_id}")
            await pubsub.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
