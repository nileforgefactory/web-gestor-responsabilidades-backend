"""Endpoints del slice SGR — Caja de Herramientas SGR Cat. 5 y 6."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.dependencies import get_rag_service
from app.slices.auth.dependencies import CurrentUser, get_current_user, require_write
from app.slices.sgr.models import ProyectoSGR
from app.slices.sgr.schemas import EvaluarPlanResponse, ProyectoSGROut
from app.slices.sgr.service import evaluar_plan_sgr
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sgr",
    tags=["sgr"],
    dependencies=[Depends(get_current_user), Depends(require_write)],
)


@router.get(
    "/evaluar-plan/{plan_id}",
    response_model=EvaluarPlanResponse,
    summary="Modo 1: evaluar brechas del plan y generar candidatos SGR",
    description=(
        "Toma las brechas detectadas en el análisis del plan de desarrollo "
        "y evalúa cuáles pueden convertirse en proyectos SGR elegibles para "
        "municipios de categoría 5 y 6. Devuelve TOP N candidatos con score de viabilidad.\n\n"
        "**Prerequisito:** el plan debe haber sido analizado (`/analysis/analyze-document`). "
        "La evaluación corre el agente de elegibilidad SGR sobre cada brecha en paralelo."
    ),
    responses={
        404: {"description": "Plan no encontrado"},
        503: {"description": "MySQL no configurado"},
    },
)
async def evaluar_plan(
    plan_id: str,
    current_user: CurrentUser,
    top_n: int = Query(10, ge=1, le=50, description="Número máximo de candidatos a retornar"),
    solo_elegibles: bool = Query(
        False, description="Si true, excluye proyectos no elegibles del resultado"
    ),
    guardar: bool = Query(
        True, description="Persistir candidatos como ProyectoSGR en MySQL"
    ),
    db: AsyncSession = Depends(get_db),
    rag: RagService = Depends(get_rag_service),
) -> EvaluarPlanResponse:
    """Evalúa las brechas del plan y genera candidatos de proyectos SGR."""
    settings = get_settings()

    # Enriquecer datos del municipio con el perfil del usuario autenticado
    # El service recibe http via rag.http
    try:
        response = await evaluar_plan_sgr(
            plan_id=plan_id,
            db=db,
            http=rag.http,
            settings=settings,
            top_n=top_n,
            solo_elegibles=solo_elegibles,
            guardar=guardar,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error en evaluar_plan_sgr plan=%s", plan_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Enriquecer con datos del perfil municipal del usuario si los tiene
    if current_user.divipola:
        response.municipio_codigo = current_user.divipola
    if current_user.categoria_municipio:
        response.categoria_municipio = current_user.categoria_municipio

    return response


@router.get(
    "/proyectos/{plan_id}",
    response_model=list[ProyectoSGROut],
    summary="Listar proyectos SGR generados para un plan",
    description=(
        "Devuelve los proyectos SGR persistidos en MySQL para el plan indicado. "
        "Incluye todos los modos (descubrimiento y evaluación inversa) y todos los estados."
    ),
    responses={404: {"description": "Plan no encontrado"}},
)
async def listar_proyectos(
    plan_id: str,
    modo: str | None = Query(
        None,
        description="Filtrar por modo: descubrimiento | evaluacion_inversa",
    ),
    estado: str | None = Query(
        None,
        description="Filtrar por estado: borrador | diagnosticado | en_plan | pre_validado | listo_dnp ...",
    ),
    db: AsyncSession = Depends(get_db),
) -> list[ProyectoSGROut]:
    """Lista proyectos SGR de un plan con filtros opcionales."""
    stmt = select(ProyectoSGR).where(ProyectoSGR.plan_id == plan_id)
    if modo:
        stmt = stmt.where(ProyectoSGR.modo == modo)
    if estado:
        stmt = stmt.where(ProyectoSGR.estado == estado)
    stmt = stmt.order_by(ProyectoSGR.score_sgr.desc().nullslast())

    result = await db.execute(stmt)
    proyectos = result.scalars().all()
    return [ProyectoSGROut.model_validate(p) for p in proyectos]


@router.get(
    "/proyecto/{proyecto_id}",
    response_model=ProyectoSGROut,
    summary="Detalle de un proyecto SGR",
    responses={404: {"description": "Proyecto no encontrado"}},
)
async def detalle_proyecto(
    proyecto_id: str,
    db: AsyncSession = Depends(get_db),
) -> ProyectoSGROut:
    """Devuelve el detalle completo de un proyecto SGR por su ID."""
    result = await db.execute(
        select(ProyectoSGR).where(ProyectoSGR.id == proyecto_id)
    )
    proyecto = result.scalar_one_or_none()
    if proyecto is None:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")
    return ProyectoSGROut.model_validate(proyecto)
