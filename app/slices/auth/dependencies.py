"""Dependencias FastAPI: usuario autenticado, admin y permisos de escritura."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.slices.auth.models import User
from app.slices.auth.permissions import can_write, is_admin
from app.slices.auth.repository import get_by_id
from app.slices.auth.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Credenciales no proporcionadas. Use Authorization: Bearer <token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(settings=settings, token=credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Token JWT inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token sin identificador de usuario.")

    user = await get_by_id(db, str(user_id))
    if user is None or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo.")

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Se requiere rol administrador.",
        )
    return user


async def require_write(user: User = Depends(get_current_user)) -> User:
    if not can_write(user):
        raise HTTPException(
            status_code=403,
            detail="Permiso denegado: su rol solo permite consultas de lectura.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
WriteUser = Annotated[User, Depends(require_write)]
