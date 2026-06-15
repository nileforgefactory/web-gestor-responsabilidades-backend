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

    @field_validator("email", mode="before")
    @classmethod
    def _val_email(cls, v: str) -> str:
        return _normalize_email_value(v)


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
