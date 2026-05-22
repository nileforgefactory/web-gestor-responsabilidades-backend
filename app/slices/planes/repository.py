"""Acceso a datos para Planes — queries async SQLAlchemy."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.slices.planes.models import (
    Brecha,
    MatrizCompetencia,
    Plane,
    PlanActor,
    PlanNorma,
    PlanSector,
    Responsabilidad,
)
from app.slices.planes.schemas import (
    ActorIn,
    BrechaIn,
    MatrizIn,
    NormaIn,
    PlanCreate,
    PlanUpdate,
    ResponsabilidadIn,
)

# ── Opciones de carga eager para evitar N+1 ──────────────────────────────

_SUMMARY_LOAD = [selectinload(Plane.sectores)]

_DETAIL_LOAD = [
    selectinload(Plane.sectores),
    selectinload(Plane.actores),
    selectinload(Plane.responsabilidades),
    selectinload(Plane.brechas),
    selectinload(Plane.matriz),
    selectinload(Plane.normas),
]


# ── Queries ───────────────────────────────────────────────────────────────

async def list_planes(
    db: AsyncSession,
    *,
    nivel: str | None = None,
    estado: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Plane]:
    stmt = (
        select(Plane)
        .options(*_SUMMARY_LOAD)
        .order_by(Plane.creado_en.desc())
        .offset(skip)
        .limit(limit)
    )
    if nivel:
        stmt = stmt.where(Plane.nivel == nivel)
    if estado:
        stmt = stmt.where(Plane.estado == estado)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_plane(db: AsyncSession, plan_id: str) -> Plane | None:
    stmt = select(Plane).options(*_DETAIL_LOAD).where(Plane.id == plan_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_plane(db: AsyncSession, data: PlanCreate) -> Plane:
    plane = Plane(
        titulo         = data.titulo,
        nombre_corto   = data.nombre_corto,
        entidad        = data.entidad,
        entidad_icono  = data.entidad_icono,
        nivel          = data.nivel,
        periodo        = data.periodo,
        estado         = data.estado,
        descripcion    = data.descripcion,
        archivo_nombre = data.archivo_nombre,
        qdrant_doc_id  = data.qdrant_doc_id,
        resp_total     = data.resp_total,
        leyes_total    = data.leyes_total,
        actores_total  = data.actores_total,
        brechas_total  = data.brechas_total,
        avance_pct     = data.avance_pct,
    )
    db.add(plane)
    await db.flush()  # genera el id antes de insertar sub-entidades

    for s in data.sectores:
        db.add(PlanSector(plan_id=plane.id, **s.model_dump()))

    for a in data.actores:
        db.add(PlanActor(plan_id=plane.id, **a.model_dump()))

    for r in data.responsabilidades:
        db.add(Responsabilidad(plan_id=plane.id, **r.model_dump()))

    for b in data.brechas:
        db.add(Brecha(plan_id=plane.id, **b.model_dump()))

    for m in data.matriz:
        db.add(MatrizCompetencia(plan_id=plane.id, **m.model_dump()))

    for n in data.normas:
        db.add(PlanNorma(plan_id=plane.id, **n.model_dump()))

    await db.flush()
    await db.commit()
    return await get_plane(db, plane.id)  # recarga con eager loading


async def update_plane(
    db: AsyncSession, plan_id: str, data: PlanUpdate
) -> Plane | None:
    plane = await db.get(Plane, plan_id)
    if plane is None:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(plane, field, value)
    await db.flush()
    await db.refresh(plane)
    return plane


async def delete_plane(db: AsyncSession, plan_id: str) -> bool:
    plane = await db.get(Plane, plan_id)
    if plane is None:
        return False
    await db.delete(plane)
    return True


async def replace_sub_entities(
    db: AsyncSession,
    plan_id: str,
    *,
    responsabilidades: list[ResponsabilidadIn],
    brechas: list[BrechaIn],
    normas: list[NormaIn],
    actores: list[ActorIn],
    matriz: list[MatrizIn],
) -> None:
    """Elimina y re-inserta todas las sub-entidades del plan en una transacción."""
    await db.execute(delete(Responsabilidad).where(Responsabilidad.plan_id == plan_id))
    await db.execute(delete(Brecha).where(Brecha.plan_id == plan_id))
    await db.execute(delete(PlanNorma).where(PlanNorma.plan_id == plan_id))
    await db.execute(delete(PlanActor).where(PlanActor.plan_id == plan_id))
    await db.execute(delete(MatrizCompetencia).where(MatrizCompetencia.plan_id == plan_id))

    for r in responsabilidades:
        db.add(Responsabilidad(plan_id=plan_id, **r.model_dump()))
    for b in brechas:
        db.add(Brecha(plan_id=plan_id, **b.model_dump()))
    for n in normas:
        db.add(PlanNorma(plan_id=plan_id, **n.model_dump()))
    for a in actores:
        db.add(PlanActor(plan_id=plan_id, **a.model_dump()))
    for m in matriz:
        db.add(MatrizCompetencia(plan_id=plan_id, **m.model_dump()))

    await db.flush()
