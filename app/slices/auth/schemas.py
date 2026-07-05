"""Esquemas Pydantic para autenticación y gestión de usuarios."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import re

from email_validator import EmailNotValidError, validate_email as _validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_FALLBACK_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email_value(v: str) -> str:
    try:
        return _validate_email(v, check_deliverability=False).normalized
    except EmailNotValidError:
        v = str(v).strip().lower()
        if _EMAIL_FALLBACK_RE.match(v):
            return v
        raise ValueError(f"Correo inválido: {v}")

RolCodigo = Literal["usuario", "administrador", "superadmin"]
RolAsignable = Literal["usuario", "administrador"]


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["superadmin@gestor.local"])
    password: str = Field(..., min_length=6, examples=["SuperAdmin123!"])

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return _normalize_email_value(v)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Segundos hasta expiración del token")


class RoleOut(BaseModel):
    id: str
    codigo: RolCodigo
    nombre: str
    descripcion: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TerritorioOut(BaseModel):
    pais: str
    departamento: str | None = None
    municipio: str | None = None
    coleccion_id: str


class MeResponse(BaseModel):
    id: str
    nombre: str
    email: str
    rol: RolCodigo
    territorio: TerritorioOut
    activo: bool
    creado_en: datetime
    plan_activo_id: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _val_email(cls, v: str) -> str:
        return _normalize_email_value(v)


class SetPlanActivoRequest(BaseModel):
    plan_id: str


class UserSummary(BaseModel):
    id: str
    nombre: str
    email: str
    rol: RolCodigo
    territorio: TerritorioOut
    activo: bool
    creado_en: datetime

    @field_validator("email", mode="before")
    @classmethod
    def _val_email(cls, v: str) -> str:
        return _normalize_email_value(v)


class ChangeRolRequest(BaseModel):
    rol: RolAsignable = Field(..., description="Nuevo rol del usuario")


# ── Onboarding SGR ─────────────────────────────────────────────────────────────

EstadoOnboarding = Literal[
    "credenciales_provisionales",
    "contrasena_cambiada",
    "plan_cargando",
    "plan_analizado",
]


class ChangePasswordRequest(BaseModel):
    """Cambio obligatorio de contraseña en el primer login (bloqueante)."""

    password_actual: str = Field(..., min_length=1, description="Contraseña actual o provisional")
    password_nuevo: str = Field(
        ...,
        min_length=10,
        description="Mínimo 10 caracteres; al menos 1 mayúscula, 1 minúscula y 1 número",
    )
    password_confirmar: str = Field(..., min_length=10)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "password_actual": "provisional123",
                    "password_nuevo": "MiClaveSegura2024",
                    "password_confirmar": "MiClaveSegura2024",
                }
            ]
        }
    )


class OnboardingStatusResponse(BaseModel):
    """Estado actual del onboarding del usuario autenticado."""

    estado: EstadoOnboarding
    password_provisional: bool
    divipola: str | None = None
    categoria_municipio: str | None = None
    nbi: float | None = None
    icld: float | None = None
    acceso_completo: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserCreateRequest(BaseModel):
    """Alta de usuario. El superadmin puede asignar cualquier territorio."""

    nombre: str = Field(..., min_length=2, max_length=200)
    email: str
    password: str = Field(..., min_length=6)
    rol: RolAsignable = "usuario"

    @field_validator("email", mode="before")
    @classmethod
    def _val_email(cls, v: str) -> str:
        return _normalize_email_value(v)
    territorio: list[str | None] | None = Field(
        None,
        description=(
            "Opcional. `[País, Departamento, Municipio]`. "
            "Si se omite, se usa el territorio del admin que crea. "
            "Solo el rol `superadmin` puede asignar otro territorio."
        ),
        json_schema_extra={
            "examples": [
                ["COLOMBIA", "HUILA", "NEIVA"],
                ["COLOMBIA", "HUILA", None],
                ["COLOMBIA", None, None],
            ]
        },
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "nombre": "Consultor Neiva",
                    "email": "consulta.neiva@gov.co",
                    "password": "clave-segura-123",
                    "rol": "usuario",
                    "territorio": ["COLOMBIA", "HUILA", "NEIVA"],
                },
                {
                    "nombre": "Admin Palermo",
                    "email": "admin.palermo@gov.co",
                    "password": "clave-segura-123",
                    "rol": "administrador",
                    "territorio": ["COLOMBIA", "HUILA", "PALERMO"],
                },
            ]
        }
    )
