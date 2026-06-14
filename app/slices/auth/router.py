"""Endpoints de autenticación y gestión de usuarios."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.openapi import RESPUESTAS_MYSQL
from app.slices.auth.dependencies import AdminUser, CurrentUser
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
    soft_delete,
    update_rol,
)
from app.slices.auth.schemas import (
    ChangeRolRequest,
    LoginRequest,
    MeResponse,
    RoleOut,
    TokenResponse,
    UserCreateRequest,
    UserSummary,
)
from app.slices.auth.security import create_access_token, hash_password, verify_password

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
