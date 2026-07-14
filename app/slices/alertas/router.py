"""Endpoints HTTP para alertas normativas."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_rag_service
from app.slices.alertas import service as alertas_svc
from app.slices.alertas.schemas import AlertaNormativaOut, MarcarLeidaRequest
from app.slices.auth.dependencies import CurrentUser, get_current_user
from app.slices.auth.permissions import ensure_collection_access
from app.slices.planes import repository as planes_repo
from app.slices.rag.service import RagService

router = APIRouter(prefix="/planes", tags=["alertas"], dependencies=[Depends(get_current_user)])


async def _plane_o_404(db: AsyncSession, current_user, plan_id: str):
    plane = await planes_repo.get_plane(db, plan_id)
    if plane is None:
        raise HTTPException(404, f"Plan '{plan_id}' no encontrado")
    ensure_collection_access(current_user, plane.coleccion_id)
    return plane


@router.get(
    "/{plan_id}/alertas",
    response_model=list[AlertaNormativaOut],
    summary="Alertas normativas del plan",
)
async def list_alertas(
    plan_id: str,
    current_user: CurrentUser,
    solo_no_leidas: bool = Query(False, description="Filtrar solo las no leídas"),
    db: AsyncSession = Depends(get_db),
) -> list[AlertaNormativaOut]:
    await _plane_o_404(db, current_user, plan_id)
    return await alertas_svc.get_alertas_plan(db, plan_id, solo_no_leidas=solo_no_leidas)  # type: ignore[return-value]


@router.post(
    "/{plan_id}/alertas/check",
    response_model=list[AlertaNormativaOut],
    summary="Verificar y generar alertas normativas",
    description=(
        "Compara las normas del plan contra el RAG en busca de modificaciones o derogaciones. "
        "Crea alertas para las normas con indicios de cambio."
    ),
)
async def check_alertas(
    plan_id: str,
    current_user: CurrentUser,
    rag: RagService = Depends(get_rag_service),
    db: AsyncSession = Depends(get_db),
) -> list[AlertaNormativaOut]:
    await _plane_o_404(db, current_user, plan_id)
    return await alertas_svc.check_normas_actualizadas(db, rag, plan_id)  # type: ignore[return-value]


@router.patch(
    "/{plan_id}/alertas/marcar-leidas",
    summary="Marcar alertas como leídas",
)
async def marcar_leidas(
    plan_id: str,
    payload: MarcarLeidaRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _plane_o_404(db, current_user, plan_id)
    count = await alertas_svc.marcar_leidas(db, payload.ids)
    return {"actualizadas": count}
