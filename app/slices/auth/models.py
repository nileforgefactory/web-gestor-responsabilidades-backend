"""Modelos SQLAlchemy de roles y usuarios."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# IDs fijos (coinciden con el seed de la migración Alembic).
ROLE_USUARIO_ID = "00000000-0000-4000-8000-000000000001"
ROLE_ADMINISTRADOR_ID = "00000000-0000-4000-8000-000000000002"
ROLE_SUPERADMIN_ID = "00000000-0000-4000-8000-000000000003"
SUPERADMIN_USER_ID = "00000000-0000-4000-8000-000000000100"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    usuarios: Mapped[list["User"]] = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        Index("idx_usuarios_coleccion", "coleccion_id"),
        Index("idx_usuarios_activo", "activo"),
        Index("idx_usuarios_rol", "rol_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id"), nullable=False
    )
    territorio: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON [País, Departamento, Municipio]",
    )
    coleccion_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Colección lógica derivada del territorio",
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── SGR: perfil municipal ──────────────────────────────────────────────
    divipola: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="Código DIVIPOLA del municipio (8 dígitos)"
    )
    categoria_municipio: Mapped[str | None] = mapped_column(
        Enum("5", "6", name="categoria_municipio_enum"),
        nullable=True,
        comment="Categoría municipal según Ley 617/2000: 5 o 6",
    )
    nbi: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="NBI del municipio (%) — DANE/Terridata"
    )
    icld: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="ICLD vigente en SMMLV — Resolución Minhacienda/CGR"
    )
    # Estado de onboarding — máquina de estados bloqueante
    estado_onboarding: Mapped[str] = mapped_column(
        Enum(
            "credenciales_provisionales",
            "contrasena_cambiada",
            "plan_cargando",
            "plan_analizado",
            name="estado_onboarding_enum",
        ),
        nullable=False,
        default="credenciales_provisionales",
        comment="Estado del onboarding obligatorio SGR",
    )
    # Marca si la contraseña es provisional (requiere cambio en primer login)
    password_provisional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    eliminado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    role: Mapped[Role] = relationship("Role", back_populates="usuarios", lazy="joined")

    @property
    def rol_codigo(self) -> str:
        return self.role.codigo if self.role else ""
