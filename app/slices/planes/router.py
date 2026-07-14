"""Endpoints HTTP CRUD de planes de desarrollo (MySQL)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.openapi import RESPUESTAS_MYSQL
from app.slices.planes import repository as repo
from app.slices.planes.schemas import (
    PlanCreate,
    PlanDetail,
    PlanSummary,
    PlanUpdate,
)

from app.slices.auth.dependencies import CurrentUser, WriteUser, get_current_user
from app.slices.auth.permissions import ensure_collection_access

router = APIRouter(
    prefix="/planes",
    tags=["planes"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/",
    response_model=list[PlanSummary],
    summary="Listar planes",
    response_description="Lista paginada de planes con resumen.",
    description="Filtra por nivel y estado territorial. Requiere MYSQL_URL.",
    responses=RESPUESTAS_MYSQL,
)
async def list_planes(
    current_user: CurrentUser,
    nivel: str | None = Query(
        None,
        description="nacional | departamental | municipal | sectorial",
    ),
    estado: str | None = Query(
        None,
        description="cargando | analizando | analizado | en-proceso | archivado",
    ),
    skip: int = Query(0, ge=0, description="Registros a omitir"),
    limit: int = Query(50, ge=1, le=200, description="Máximo de registros"),
    db: AsyncSession = Depends(get_db),
) -> list[PlanSummary]:
    """Devuelve planes ordenados por fecha de creación descendente.

    Filtra por territorio (coleccion_id) del usuario autenticado, salvo
    superadmin que ve todos los planes sin restricción.
    """
    coleccion_id = (
        None if current_user.rol_codigo == "superadmin" else current_user.coleccion_id
    )
    return await repo.list_planes(
        db, nivel=nivel, estado=estado, coleccion_id=coleccion_id, skip=skip, limit=limit
    )  # type: ignore[return-value]


@router.get(
    "/{plan_id}",
    response_model=PlanDetail,
    summary="Detalle de un plan",
    response_description="Plan con responsabilidades, leyes, actores, brechas y matriz.",
    responses={**RESPUESTAS_MYSQL, 200: {"description": "Plan encontrado."}},
)
async def get_plan(
    plan_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PlanDetail:
    """Obtiene un plan por ID con relaciones cargadas (eager)."""
    plane = await repo.get_plane(db, plan_id)
    if plane is None:
        raise HTTPException(404, f"Plan '{plan_id}' no encontrado")
    ensure_collection_access(current_user, plane.coleccion_id)
    return plane  # type: ignore[return-value]


@router.post(
    "/",
    response_model=PlanDetail,
    status_code=201,
    summary="Crear plan",
    response_description="Plan creado con ID asignado.",
    responses={**RESPUESTAS_MYSQL, 201: {"description": "Plan creado."}},
)
async def create_plan(
    payload: PlanCreate,
    _: WriteUser,
    db: AsyncSession = Depends(get_db),
) -> PlanDetail:
    """Registra un nuevo plan de desarrollo en MySQL."""
    plane = await repo.create_plane(db, payload)
    return plane  # type: ignore[return-value]


@router.patch(
    "/{plan_id}",
    response_model=PlanSummary,
    summary="Actualizar plan",
    response_description="Campos actualizados del plan.",
    responses=RESPUESTAS_MYSQL,
)
async def update_plan(
    plan_id: str,
    payload: PlanUpdate,
    current_user: WriteUser,
    db: AsyncSession = Depends(get_db),
) -> PlanSummary:
    """Actualización parcial de metadatos del plan."""
    existente = await db.get(repo.Plane, plan_id)
    if existente is None:
        raise HTTPException(404, f"Plan '{plan_id}' no encontrado")
    ensure_collection_access(current_user, existente.coleccion_id)

    plane = await repo.update_plane(db, plan_id, payload)
    return plane  # type: ignore[return-value]


@router.delete(
    "/{plan_id}",
    status_code=204,
    summary="Eliminar plan",
    description="Elimina el plan y sus registros hijos (CASCADE).",
    responses={**RESPUESTAS_MYSQL, 204: {"description": "Plan eliminado."}},
)
async def delete_plan(
    plan_id: str,
    current_user: WriteUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Elimina un plan por ID."""
    existente = await db.get(repo.Plane, plan_id)
    if existente is None:
        raise HTTPException(404, f"Plan '{plan_id}' no encontrado")
    ensure_collection_access(current_user, existente.coleccion_id)

    await repo.delete_plane(db, plan_id)
