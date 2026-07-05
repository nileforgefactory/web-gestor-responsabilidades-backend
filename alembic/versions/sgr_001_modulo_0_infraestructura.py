"""SGR M0: infraestructura base — campos usuario, brecha y nuevas tablas SGR

Revision ID: sgr001
Revises: a1b2c3d4e5f6
Create Date: 2026-07-02

Cambios:
- usuarios: divipola, categoria_municipio, nbi, icld, estado_onboarding, password_provisional
- brechas: elegibilidad_sgr, sector_sgr
- nueva tabla costos_referencia_sgr
- nueva tabla proyectos_sgr
- nueva tabla fichas_mga
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "sgr001"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _table_exists(connection: sa.Connection, name: str) -> bool:
    return name in sa.inspect(connection).get_table_names()


def _column_exists(connection: sa.Connection, table: str, column: str) -> bool:
    if not _table_exists(connection, table):
        return False
    cols = {c["name"] for c in sa.inspect(connection).get_columns(table)}
    return column in cols


def _index_exists(connection: sa.Connection, table: str, index_name: str) -> bool:
    if not _table_exists(connection, table):
        return False
    idxs = {i["name"] for i in sa.inspect(connection).get_indexes(table)}
    return index_name in idxs


def upgrade() -> None:
    # Migración idempotente: en bases nuevas, 0001_initial_schema (create_all
    # desde el estado actual de los modelos) ya crea estas columnas/tablas.
    # Estas comprobaciones evitan "Duplicate column/table" en ese caso, y
    # siguen aplicando los cambios en bases existentes que aún no los tienen.
    connection = op.get_bind()

    # ── 1. Nuevos enums ────────────────────────────────────────────────────
    # MySQL no requiere CREATE TYPE; los enums se definen inline en la columna.
    # SQLAlchemy los genera como ENUM('v1','v2',...) directamente.

    # ── 2. Columnas en usuarios ────────────────────────────────────────────
    if not _column_exists(connection, "usuarios", "divipola"):
        op.add_column(
            "usuarios",
            sa.Column("divipola", sa.String(8), nullable=True,
                      comment="Código DIVIPOLA del municipio (8 dígitos)"),
        )
    if not _column_exists(connection, "usuarios", "categoria_municipio"):
        op.add_column(
            "usuarios",
            sa.Column(
                "categoria_municipio",
                sa.Enum("5", "6", name="categoria_municipio_enum"),
                nullable=True,
                comment="Categoría municipal según Ley 617/2000: 5 o 6",
            ),
        )
    if not _column_exists(connection, "usuarios", "nbi"):
        op.add_column(
            "usuarios",
            sa.Column("nbi", sa.Float(), nullable=True,
                      comment="NBI del municipio (%) — DANE/Terridata"),
        )
    if not _column_exists(connection, "usuarios", "icld"):
        op.add_column(
            "usuarios",
            sa.Column("icld", sa.Float(), nullable=True,
                      comment="ICLD vigente en SMMLV — Resolución Minhacienda/CGR"),
        )
    if not _column_exists(connection, "usuarios", "estado_onboarding"):
        op.add_column(
            "usuarios",
            sa.Column(
                "estado_onboarding",
                sa.Enum(
                    "credenciales_provisionales",
                    "contrasena_cambiada",
                    "plan_cargando",
                    "plan_analizado",
                    name="estado_onboarding_enum",
                ),
                nullable=False,
                server_default="credenciales_provisionales",
                comment="Estado del onboarding obligatorio SGR",
            ),
        )
    if not _column_exists(connection, "usuarios", "password_provisional"):
        op.add_column(
            "usuarios",
            sa.Column(
                "password_provisional",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )

    # ── 3. Columnas en brechas ─────────────────────────────────────────────
    if not _column_exists(connection, "brechas", "elegibilidad_sgr"):
        op.add_column(
            "brechas",
            sa.Column("elegibilidad_sgr", sa.Boolean(), nullable=True),
        )
    if not _column_exists(connection, "brechas", "sector_sgr"):
        op.add_column(
            "brechas",
            sa.Column("sector_sgr", sa.String(80), nullable=True),
        )

    # ── 4. Tabla costos_referencia_sgr ─────────────────────────────────────
    costos_ya_existia = _table_exists(connection, "costos_referencia_sgr")
    if not costos_ya_existia:
        op.create_table(
            "costos_referencia_sgr",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("sector_sgr", sa.String(80), nullable=False),
            sa.Column("tipo_inversion", sa.String(120), nullable=False),
            sa.Column("unidad_medida", sa.String(50), nullable=False),
            sa.Column(
                "region_geografica",
                sa.Enum("Andes", "Caribe", "Pacifico", "Amazonia", "Orinoquia",
                        name="region_geo_enum"),
                nullable=False,
            ),
            sa.Column("departamento", sa.String(100), nullable=True),
            sa.Column("valor_minimo", sa.Float(), nullable=False),
            sa.Column("valor_promedio", sa.Float(), nullable=False),
            sa.Column("valor_maximo", sa.Float(), nullable=False),
            sa.Column("fuente", sa.String(200), nullable=False),
            sa.Column("anio_referencia", sa.Integer(), nullable=False),
            sa.Column("vigente", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("actualizado_en", sa.DateTime(), server_default=sa.func.now(),
                      onupdate=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists(connection, "costos_referencia_sgr", "idx_costos_sector_region"):
        op.create_index(
            "idx_costos_sector_region",
            "costos_referencia_sgr",
            ["sector_sgr", "region_geografica"],
        )

    # ── 5. Tabla proyectos_sgr ─────────────────────────────────────────────
    proyectos_ya_existia = _table_exists(connection, "proyectos_sgr")
    if not proyectos_ya_existia:
        op.create_table(
            "proyectos_sgr",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("plan_id", sa.String(36), nullable=False),
            sa.Column("brecha_id", sa.Integer(), nullable=True),
            sa.Column("municipio_codigo", sa.String(8), nullable=False),
            sa.Column("nombre", sa.Text(), nullable=False),
            sa.Column("descripcion_problema", sa.Text(), nullable=True),
            sa.Column("sector_sgr", sa.String(80), nullable=False),
            sa.Column("subsector_sgr", sa.String(120), nullable=True),
            sa.Column("tipo_inversion", sa.String(120), nullable=True),
            sa.Column(
                "fuente_sgr",
                sa.Enum(
                    "inversion_local", "asignacion_directa", "inversion_regional",
                    "ctei", "paz", "ambiental",
                    name="fuente_sgr_enum",
                ),
                nullable=True,
            ),
            sa.Column("score_sgr", sa.Float(), nullable=True),
            sa.Column("score_severidad", sa.Float(), nullable=True),
            sa.Column("score_alineacion", sa.Float(), nullable=True),
            sa.Column("score_elegibilidad", sa.Float(), nullable=True),
            sa.Column("score_viabilidad", sa.Float(), nullable=True),
            sa.Column("elegible", sa.Boolean(), nullable=True),
            sa.Column("razon_elegibilidad", sa.Text(), nullable=True),
            sa.Column(
                "cuadrante",
                sa.Enum(
                    "optimo", "bien_justificado", "atractivo_con_riesgo", "reformular",
                    name="cuadrante_sgr_enum",
                ),
                nullable=True,
            ),
            sa.Column("resultado_duplicidad", sa.JSON(), nullable=True),
            sa.Column("validacion_costos", sa.JSON(), nullable=True),
            sa.Column("diagnostico_mga", sa.JSON(), nullable=True),
            sa.Column("en_plan", sa.Boolean(), nullable=True),
            sa.Column("chunks_respaldo", sa.Text(), nullable=True),
            sa.Column("texto_inclusion_sugerido", sa.Text(), nullable=True),
            sa.Column(
                "estado",
                sa.Enum(
                    "borrador", "diagnosticado", "pendiente_plan", "en_plan",
                    "pre_validado", "listo_dnp", "enviado_dnp", "aprobado", "rechazado",
                    name="estado_proyecto_sgr_enum",
                ),
                nullable=False,
                server_default="borrador",
            ),
            sa.Column(
                "modo",
                sa.Enum("descubrimiento", "evaluacion_inversa", name="modo_sgr_enum"),
                nullable=False,
                server_default="descubrimiento",
            ),
            sa.Column("creado_en", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("actualizado_en", sa.DateTime(), server_default=sa.func.now(),
                      onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(["plan_id"], ["planes.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["brecha_id"], ["brechas.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists(connection, "proyectos_sgr", "idx_proyecto_plan"):
        op.create_index("idx_proyecto_plan", "proyectos_sgr", ["plan_id"])
    if not _index_exists(connection, "proyectos_sgr", "idx_proyecto_municipio"):
        op.create_index("idx_proyecto_municipio", "proyectos_sgr", ["municipio_codigo"])
    if not _index_exists(connection, "proyectos_sgr", "idx_proyecto_estado"):
        op.create_index("idx_proyecto_estado", "proyectos_sgr", ["estado"])

    # ── 6. Tabla fichas_mga ────────────────────────────────────────────────
    fichas_ya_existia = _table_exists(connection, "fichas_mga")
    if not fichas_ya_existia:
        op.create_table(
            "fichas_mga",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("proyecto_id", sa.String(36), nullable=False),
            sa.Column("identificacion", sa.Text(), nullable=True),
            sa.Column("preparacion", sa.Text(), nullable=True),
            sa.Column("evaluacion", sa.Text(), nullable=True),
            sa.Column("programacion", sa.Text(), nullable=True),
            sa.Column("campos_completos", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("modelo_usado", sa.String(100), nullable=True),
            sa.Column("tokens_usados", sa.Integer(), nullable=True),
            sa.Column("generado_en", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("actualizado_en", sa.DateTime(), server_default=sa.func.now(),
                      onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos_sgr.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("proyecto_id"),
        )

    # ── 7. Seed de costos de referencia SGR (valores orientativos DNP 2024) ─
    # Solo sembrar si la tabla no traía datos (evita duplicar el seed si esta
    # migración se reintenta tras un fallo parcial, o si create_all ya la
    # creó vacía en una base nueva).
    costos_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM costos_referencia_sgr")
    ).scalar()
    if costos_count:
        return

    costos_table = sa.table(
        "costos_referencia_sgr",
        sa.column("sector_sgr", sa.String),
        sa.column("tipo_inversion", sa.String),
        sa.column("unidad_medida", sa.String),
        sa.column("region_geografica", sa.String),
        sa.column("valor_minimo", sa.Float),
        sa.column("valor_promedio", sa.Float),
        sa.column("valor_maximo", sa.Float),
        sa.column("fuente", sa.String),
        sa.column("anio_referencia", sa.Integer),
        sa.column("vigente", sa.Boolean),
    )
    op.bulk_insert(costos_table, [
        # Agua potable
        {
            "sector_sgr": "Agua potable y saneamiento",
            "tipo_inversion": "Acueducto veredal",
            "unidad_medida": "usuario",
            "region_geografica": "Andes",
            "valor_minimo": 3_500_000,
            "valor_promedio": 5_200_000,
            "valor_maximo": 7_800_000,
            "fuente": "DNP precios unitarios sectoriales 2024",
            "anio_referencia": 2024,
            "vigente": True,
        },
        {
            "sector_sgr": "Agua potable y saneamiento",
            "tipo_inversion": "Acueducto veredal",
            "unidad_medida": "usuario",
            "region_geografica": "Caribe",
            "valor_minimo": 3_200_000,
            "valor_promedio": 4_800_000,
            "valor_maximo": 7_200_000,
            "fuente": "DNP precios unitarios sectoriales 2024",
            "anio_referencia": 2024,
            "vigente": True,
        },
        {
            "sector_sgr": "Agua potable y saneamiento",
            "tipo_inversion": "Alcantarillado",
            "unidad_medida": "metro lineal",
            "region_geografica": "Andes",
            "valor_minimo": 850_000,
            "valor_promedio": 1_300_000,
            "valor_maximo": 2_100_000,
            "fuente": "DNP precios unitarios sectoriales 2024",
            "anio_referencia": 2024,
            "vigente": True,
        },
        # Transporte
        {
            "sector_sgr": "Transporte",
            "tipo_inversion": "Vía terciaria (mejoramiento)",
            "unidad_medida": "km",
            "region_geografica": "Andes",
            "valor_minimo": 280_000_000,
            "valor_promedio": 420_000_000,
            "valor_maximo": 650_000_000,
            "fuente": "DNP precios unitarios sectoriales 2024",
            "anio_referencia": 2024,
            "vigente": True,
        },
        {
            "sector_sgr": "Transporte",
            "tipo_inversion": "Vía terciaria (mejoramiento)",
            "unidad_medida": "km",
            "region_geografica": "Amazonia",
            "valor_minimo": 380_000_000,
            "valor_promedio": 580_000_000,
            "valor_maximo": 900_000_000,
            "fuente": "DNP precios unitarios sectoriales 2024",
            "anio_referencia": 2024,
            "vigente": True,
        },
        # Educación
        {
            "sector_sgr": "Educación",
            "tipo_inversion": "Aula escolar nueva",
            "unidad_medida": "aula",
            "region_geografica": "Andes",
            "valor_minimo": 180_000_000,
            "valor_promedio": 260_000_000,
            "valor_maximo": 380_000_000,
            "fuente": "MinEducación precios unitarios 2024",
            "anio_referencia": 2024,
            "vigente": True,
        },
        # Salud
        {
            "sector_sgr": "Salud",
            "tipo_inversion": "Centro de salud (adecuación)",
            "unidad_medida": "m2",
            "region_geografica": "Andes",
            "valor_minimo": 1_800_000,
            "valor_promedio": 2_600_000,
            "valor_maximo": 3_800_000,
            "fuente": "MinSalud precios de referencia 2024",
            "anio_referencia": 2024,
            "vigente": True,
        },
        # Deporte y recreación
        {
            "sector_sgr": "Deporte y recreación",
            "tipo_inversion": "Cancha múltiple",
            "unidad_medida": "unidad",
            "region_geografica": "Andes",
            "valor_minimo": 180_000_000,
            "valor_promedio": 280_000_000,
            "valor_maximo": 420_000_000,
            "fuente": "Coldeportes / MinDeporte precios referencia 2024",
            "anio_referencia": 2024,
            "vigente": True,
        },
    ])


def downgrade() -> None:
    op.drop_table("fichas_mga")
    op.drop_index("idx_proyecto_estado", "proyectos_sgr")
    op.drop_index("idx_proyecto_municipio", "proyectos_sgr")
    op.drop_index("idx_proyecto_plan", "proyectos_sgr")
    op.drop_table("proyectos_sgr")
    op.drop_index("idx_costos_sector_region", "costos_referencia_sgr")
    op.drop_table("costos_referencia_sgr")

    op.drop_column("brechas", "sector_sgr")
    op.drop_column("brechas", "elegibilidad_sgr")

    op.drop_column("usuarios", "password_provisional")
    op.drop_column("usuarios", "estado_onboarding")
    op.drop_column("usuarios", "icld")
    op.drop_column("usuarios", "nbi")
    op.drop_column("usuarios", "categoria_municipio")
    op.drop_column("usuarios", "divipola")
