"""Endpoints HTTP para Planes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.slices.planes import repository as repo
from app.slices.planes.schemas import (
    PlanCreate,
    PlanDetail,
    PlanSummary,
    PlanUpdate,
)

router = APIRouter(prefix="/planes", tags=["planes"])


@router.get("/", response_model=list[PlanSummary], summary="Listar planes")
async def list_planes(
    nivel:  str | None = Query(None, description="nacional | departamental | municipal | sectorial"),
    estado: str | None = Query(None, description="cargando | analizando | analizado | en-proceso | archivado"),
    skip:   int        = Query(0,    ge=0),
    limit:  int        = Query(50,   ge=1, le=200),
    db: AsyncSession   = Depends(get_db),
) -> list[PlanSummary]:
    return await repo.list_planes(db, nivel=nivel, estado=estado, skip=skip, limit=limit)  # type: ignore[return-value]


@router.get("/{plan_id}", response_model=PlanDetail, summary="Detalle de un plan")
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db)) -> PlanDetail:
    plane = await repo.get_plane(db, plan_id)
    if plane is None:
        raise HTTPException(404, f"Plan '{plan_id}' no encontrado")
    return plane  # type: ignore[return-value]


@router.post("/", response_model=PlanDetail, status_code=201, summary="Crear plan")
async def create_plan(
    payload: PlanCreate, db: AsyncSession = Depends(get_db)
) -> PlanDetail:
    plane = await repo.create_plane(db, payload)
    return plane  # type: ignore[return-value]


@router.patch("/{plan_id}", response_model=PlanSummary, summary="Actualizar plan")
async def update_plan(
    plan_id: str, payload: PlanUpdate, db: AsyncSession = Depends(get_db)
) -> PlanSummary:
    plane = await repo.update_plane(db, plan_id, payload)
    if plane is None:
        raise HTTPException(404, f"Plan '{plan_id}' no encontrado")
    return plane  # type: ignore[return-value]


@router.delete("/{plan_id}", status_code=204, summary="Eliminar plan")
async def delete_plan(plan_id: str, db: AsyncSession = Depends(get_db)) -> None:
    deleted = await repo.delete_plane(db, plan_id)
    if not deleted:
        raise HTTPException(404, f"Plan '{plan_id}' no encontrado")
