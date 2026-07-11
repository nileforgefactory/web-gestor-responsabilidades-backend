"""Endpoints de autenticación y gestión de usuarios."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.openapi import RESPUESTAS_MYSQL
from app.dependencies import get_rag_service
from app.slices.auth.dependencies import AdminUser, CurrentUser
from app.slices.common.divipola_search import buscar_municipios
from app.slices.rag.service import RagService
from app.slices.auth.mappers import to_me_response, to_user_summary
from app.slices.auth.permissions import (
    ensure_can_manage_user,
    is_superadmin,
    resolve_territorio_for_creation,
    rol_codigo,
)
from app.slices.auth.repository import (
    create_user,
    get_by_email,
    get_by_id,
    list_all_active,
    list_by_territory,
    list_roles,
    set_plan_activo,
    soft_delete,
    update_rol,
)
from app.slices.auth.schemas import (
    ChangePasswordRequest,
    ChangeRolRequest,
    LoginRequest,
    MeResponse,
    OnboardingStatusResponse,
    RoleOut,
    SetPlanActivoRequest,
    TokenResponse,
    UserCreateRequest,
    UserSummary,
)
from app.slices.auth.security import create_access_token, hash_password, verify_password
from app.slices.planes.models import Plane

router = APIRouter(tags=["auth"])

RESPUESTAS_AUTH: dict = {
    **RESPUESTAS_MYSQL,
    401: {"description": "Token ausente, inválido o expirado."},
    403: {"description": "Permiso denegado (rol o territorio)."},
}


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Iniciar sesión y obtener JWT",
    description=(
        "Autentica con correo y contraseña. Use el `access_token` en Swagger "
        "con el botón **Authorize** → esquema **BearerAuth**."
    ),
    responses=RESPUESTAS_AUTH,
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    user = await get_by_email(db, payload.email)
    if user is None or not user.activo:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")

    token, expires_in = create_access_token(
        settings=settings,
        subject=user.id,
        extra_claims={"rol": rol_codigo(user), "coleccion_id": user.coleccion_id},
    )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Perfil del usuario autenticado",
    description="Devuelve nombre, correo, rol y territorio del token JWT.",
    responses=RESPUESTAS_AUTH,
)
async def get_me(current_user: CurrentUser) -> MeResponse:
    return to_me_response(current_user)


@router.patch(
    "/me/plan-activo",
    response_model=MeResponse,
    summary="Seleccionar plan activo",
    description="Define el plan sobre el que trabajara el usuario en los flujos SGR (ej. Evaluacion Inversa).",
    responses=RESPUESTAS_AUTH,
)
async def set_plan_activo_endpoint(
    payload: SetPlanActivoRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    result = await db.execute(select(Plane).where(Plane.id == payload.plan_id))
    plane = result.scalar_one_or_none()
    if plane is None:
        raise HTTPException(status_code=404, detail="Plan no encontrado.")

    if current_user.rol_codigo != "superadmin":
        if plane.coleccion_id is None or plane.coleccion_id != current_user.coleccion_id:
            raise HTTPException(status_code=403, detail="No tiene acceso a este plan.")

    usuario_actualizado = await set_plan_activo(db, current_user, payload.plan_id)
    return to_me_response(usuario_actualizado)


@router.get(
    "/roles",
    response_model=list[RoleOut],
    summary="Listar roles del sistema",
    description="Roles disponibles en la tabla `roles` (usuario, administrador, superadmin).",
    responses=RESPUESTAS_AUTH,
)
async def get_roles(
    _: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> list[RoleOut]:
    roles = await list_roles(db)
    return [
        RoleOut(
            id=r.id,
            codigo=r.codigo,  # type: ignore[arg-type]
            nombre=r.nombre,
            descripcion=r.descripcion,
        )
        for r in roles
    ]


@router.get(
    "/users",
    response_model=list[UserSummary],
    summary="Listar usuarios (admin)",
    description=(
        "Administradores territoriales: usuarios activos de su territorio. "
        "Superadmin: todos los usuarios activos (filtro opcional `coleccion_id`)."
    ),
    responses=RESPUESTAS_AUTH,
)
async def list_users(
    admin: AdminUser,
    coleccion_id: str | None = Query(
        None,
        description="Filtro por colección (solo superadmin)",
    ),
    db: AsyncSession = Depends(get_db),
) -> list[UserSummary]:
    if is_superadmin(admin):
        users = await list_all_active(db, coleccion_id=coleccion_id)
    else:
        if coleccion_id and coleccion_id.upper() != admin.coleccion_id:
            raise HTTPException(
                status_code=403,
                detail="No puede listar usuarios de otro territorio.",
            )
        users = await list_by_territory(db, coleccion_id=admin.coleccion_id)
    return [to_user_summary(u) for u in users]


@router.get(
    "/territorio/municipios",
    summary="Buscar municipios en línea (DIVIPOLA + categoría SGR)",
    description=(
        "Busca departamento/municipio en línea contra el dataset DIVIPOLA de "
        "datos.gov.co y enriquece cada resultado con la categoría municipal "
        "(Ley 617/2000) del catálogo embebido, para asignarla al crear un usuario."
    ),
    responses=RESPUESTAS_AUTH,
)
async def buscar_municipios_endpoint(
    admin: AdminUser,
    q: str = Query(..., min_length=2, description="Texto de búsqueda (municipio o departamento)"),
    rag: RagService = Depends(get_rag_service),
) -> list[dict]:
    return await buscar_municipios(q, http=rag.http)


@router.post(
    "/users",
    response_model=UserSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario (admin)",
    description=(
        "Alta de `usuario` o `administrador`. "
        "El **superadmin** (creado en migración) puede enviar `territorio` "
        "para provisionar cuentas en cualquier colección."
    ),
    responses={**RESPUESTAS_AUTH, 201: {"description": "Usuario creado."}},
)
async def create_user_endpoint(
    payload: UserCreateRequest,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> UserSummary:
    existing = await get_by_email(db, payload.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo.")

    territorio = resolve_territorio_for_creation(admin, payload.territorio)
    try:
        user = await create_user(
            db,
            nombre=payload.nombre,
            email=payload.email,
            password_hash=hash_password(payload.password),
            rol_codigo=payload.rol,
            territorio_raw=territorio,
            divipola=payload.divipola,
            categoria_municipio=payload.categoria_municipio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_user_summary(user)


@router.put(
    "/user/{user_id}/change-rol",
    response_model=UserSummary,
    summary="Cambiar rol de un usuario (admin)",
    description="Administrador territorial (mismo territorio) o superadmin (cualquier usuario).",
    responses=RESPUESTAS_AUTH,
)
async def change_user_rol(
    user_id: str,
    payload: ChangeRolRequest,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> UserSummary:
    target = await get_by_id(db, user_id)
    if target is None or not target.activo:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    ensure_can_manage_user(admin, target)
    if target.id == admin.id and rol_codigo(target) == "superadmin":
        raise HTTPException(
            status_code=400,
            detail="No puede cambiar su propio rol de superadmin.",
        )
    if rol_codigo(target) == "superadmin":
        raise HTTPException(
            status_code=400,
            detail="No se puede cambiar el rol de un superadmin.",
        )
    try:
        updated = await update_rol(db, target, payload.rol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_user_summary(updated)


@router.delete(
    "/user/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar usuario (soft delete, admin)",
    description="Marca al usuario como inactivo. Superadmin puede eliminar en cualquier territorio.",
    responses={**RESPUESTAS_AUTH, 204: {"description": "Usuario desactivado."}},
)
async def delete_user(
    user_id: str,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    target = await get_by_id(db, user_id)
    if target is None or not target.activo:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    ensure_can_manage_user(admin, target)
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="No puede eliminar su propia cuenta.")
    if rol_codigo(target) == "superadmin":
        raise HTTPException(status_code=400, detail="No se puede eliminar un superadmin.")
    await soft_delete(db, target)


# ── Onboarding SGR ─────────────────────────────────────────────────────────────

_PW_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{10,}$")


@router.get(
    "/onboarding-status",
    response_model=OnboardingStatusResponse,
    summary="Estado del onboarding SGR del usuario autenticado",
    description=(
        "Devuelve el estado actual del flujo de onboarding bloqueante: "
        "`credenciales_provisionales → contrasena_cambiada → plan_cargando → plan_analizado`."
    ),
    responses=RESPUESTAS_AUTH,
)
async def get_onboarding_status(current_user: CurrentUser) -> OnboardingStatusResponse:
    return OnboardingStatusResponse(
        estado=current_user.estado_onboarding,  # type: ignore[arg-type]
        password_provisional=current_user.password_provisional,
        divipola=current_user.divipola,
        categoria_municipio=current_user.categoria_municipio,
        nbi=current_user.nbi,
        icld=current_user.icld,
        acceso_completo=current_user.estado_onboarding == "plan_analizado",
    )


@router.post(
    "/change-password",
    response_model=OnboardingStatusResponse,
    summary="Cambiar contraseña (obligatorio en primer login)",
    description=(
        "Valida la contraseña actual, aplica las reglas de seguridad y actualiza el estado "
        "de onboarding a `contrasena_cambiada`. "
        "La nueva contraseña debe tener mínimo 10 caracteres con al menos "
        "una mayúscula, una minúscula y un número."
    ),
    responses={**RESPUESTAS_AUTH, 400: {"description": "Validación fallida."}},
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusResponse:
    # Verificar contraseña actual
    if not verify_password(payload.password_actual, current_user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta.")

    # No puede ser igual a la provisional
    if verify_password(payload.password_nuevo, current_user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña no puede ser igual a la contraseña actual.",
        )

    # Confirmación
    if payload.password_nuevo != payload.password_confirmar:
        raise HTTPException(
            status_code=400, detail="Las contraseñas nuevas no coinciden."
        )

    # Regla de complejidad
    if not _PW_RE.match(payload.password_nuevo):
        raise HTTPException(
            status_code=400,
            detail=(
                "La contraseña debe tener mínimo 10 caracteres, "
                "al menos una mayúscula, una minúscula y un número."
            ),
        )

    # No puede contener el nombre del municipio ni el DIVIPOLA
    pw_lower = payload.password_nuevo.lower()
    if current_user.divipola and current_user.divipola in payload.password_nuevo:
        raise HTTPException(
            status_code=400,
            detail="La contraseña no puede contener el código DIVIPOLA del municipio.",
        )

    # Actualizar en DB
    current_user.password_hash = hash_password(payload.password_nuevo)
    current_user.password_provisional = False
    if current_user.estado_onboarding == "credenciales_provisionales":
        current_user.estado_onboarding = "contrasena_cambiada"  # type: ignore[assignment]

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return OnboardingStatusResponse(
        estado=current_user.estado_onboarding,  # type: ignore[arg-type]
        password_provisional=current_user.password_provisional,
        divipola=current_user.divipola,
        categoria_municipio=current_user.categoria_municipio,
        nbi=current_user.nbi,
        icld=current_user.icld,
        acceso_completo=current_user.estado_onboarding == "plan_analizado",
    )
