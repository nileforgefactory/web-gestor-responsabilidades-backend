import logging

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import get_rag_service
from app.slices.rag.extract import (
    derive_document_id_from_filename,
    extract_text_from_upload,
    extract_title,
)
from app.slices.rag.schemas import (
    AgentContextRequest,
    AgentContextResponse,
    AskRequest,
    AskResponse,
    IngestTextRequest,
    IngestTextResponse,
    RagSearchRequest,
    RagSearchResponse,
)
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

_ASK_BODY_EXAMPLES: dict[str, dict] = {
    "demo_demo_local": {
        "summary": "Pregunta demo (coleccion demo_local)",
        "description": (
            "Ingesta antes `demo_policies` con collection_id=demo_local, "
            "o texto equivalente con la misma coleccion."
        ),
        "value": {
            "collection_ids": ["demo_local"],
            "user_message": "Cual es el SLA de primera respuesta para un incidente P1?",
            "top_k": 5,
        },
    },
}

router = APIRouter(prefix="/rag", tags=["rag"])


def _upstream_http(exc: BaseException, *, code: int) -> HTTPException:
    return HTTPException(
        status_code=code,
        detail=(
            f"No se pudo completar la operacion (upstream): {exc!s}. "
            f"Sugerencia GET /health/ready y revisar logs docker: api-rag-ollama, api-rag-api."
        ),
    )


@router.post("/ingest-text", response_model=IngestTextResponse)
async def ingest_text(
    payload: IngestTextRequest, service: RagService = Depends(get_rag_service)
) -> IngestTextResponse:
    await service.ensure_collection()
    try:
        return await service.ingest_text(
            collection_id=payload.collection_id,
            document_id=payload.document_id,
            content=payload.content,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
            title=payload.document_id,
            source_filename=None,
        )
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo ingest_text")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ingest-file", response_model=IngestTextResponse)
async def ingest_file(
    collection_id: str = Form(..., min_length=1),
    document_id: str | None = Form(None),
    chunk_size: int = Form(700, ge=200, le=8000),
    chunk_overlap: int = Form(120, ge=0, le=2000),
    file: UploadFile = File(...),
    service: RagService = Depends(get_rag_service),
) -> IngestTextResponse:
    await service.ensure_collection()
    try:
        text, filename = await extract_text_from_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    doc_id = (document_id or "").strip() or derive_document_id_from_filename(filename)
    title = extract_title(filename)
    try:
        return await service.ingest_text(
            collection_id=collection_id,
            document_id=doc_id,
            content=text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            title=title,
            source_filename=filename,
        )
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo ingest_file")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/search", response_model=RagSearchResponse)
async def search(
    payload: RagSearchRequest, service: RagService = Depends(get_rag_service)
) -> RagSearchResponse:
    await service.ensure_collection()
    try:
        return await service.search(
            query=payload.query,
            collection_ids=payload.collection_ids,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
        )
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo search")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/agent-context", response_model=AgentContextResponse)
async def agent_context(
    payload: AgentContextRequest, service: RagService = Depends(get_rag_service)
) -> AgentContextResponse:
    await service.ensure_collection()
    try:
        return await service.build_agent_context(
            user_message=payload.user_message,
            collection_ids=payload.collection_ids,
            top_k=payload.top_k,
        )
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo agent_context")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ask", response_model=AskResponse)
async def rag_ask(
    payload: AskRequest = Body(
        openapi_examples=_ASK_BODY_EXAMPLES,
        description="Consulta conversacional usando solo evidencia recuperada + modelo local en Ollama.",
    ),
    service: RagService = Depends(get_rag_service),
) -> AskResponse:
    await service.ensure_collection()
    try:
        return await service.ask(
            user_message=payload.user_message,
            collection_ids=payload.collection_ids,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Tiempo agotado hablando con Ollama ({exc!s}). "
                "Swagger puede tardar; reintenta. CPU local + modelos grandes exigen espera prolongada."
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo rag_ask")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
