"""Schemas Pydantic para el slice SGR."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Elegibilidad ───────────────────────────────────────────────────────────────

class ElegibilidadResult(BaseModel):
    brecha_id: int
    brecha_titulo: str
    brecha_severidad: str
    brecha_sector: str
    elegible: bool
    condicional: bool = False
    sector_sgr: str
    subsector: str | None = None
    fuente_recomendada: str
    fuente_label: str
    razon: str
    condiciones: list[str] = Field(default_factory=list)
    tipo_inversion: str = ""


# ── Scoring ────────────────────────────────────────────────────────────────────

class ProyectoCandidatoResponse(BaseModel):
    """Proyecto SGR candidato con score de viabilidad — output del Modo 1."""

    # Datos del proyecto
    id: str | None = None
    brecha_id: int
    brecha_titulo: str
    brecha_severidad: str
    nombre: str
    sector_sgr: str
    subsector: str | None = None
    tipo_inversion: str
    fuente_recomendada: str
    fuente_label: str
    razon_elegibilidad: str
    condiciones: list[str] = Field(default_factory=list)

    # Scoring
    score_sgr: float = Field(..., ge=0.0, le=1.0, description="Score de viabilidad 0–1")
    score_severidad: float
    score_alineacion: float
    score_elegibilidad: float
    score_viabilidad: float

    # Semáforo
    semaforo: str = Field(..., description="verde | amarillo | rojo")
    semaforo_label: str

    # Estado y modo
    estado: str = "borrador"
    modo: str = "descubrimiento"

    model_config = ConfigDict(from_attributes=True)


class EvaluarPlanResponse(BaseModel):
    """Respuesta del endpoint GET /sgr/evaluar-plan/{plan_id}."""

    plan_id: str
    municipio_codigo: str | None
    categoria_municipio: str | None
    total_brechas: int
    total_elegibles: int
    total_no_elegibles: int
    proyectos_candidatos: list[ProyectoCandidatoResponse]
    advertencias: list[str] = Field(default_factory=list)
    procesado_en: datetime = Field(default_factory=datetime.utcnow)


# ── Proyecto SGR (CRUD básico) ─────────────────────────────────────────────────

class ProyectoSGROut(BaseModel):
    id: str
    plan_id: str
    brecha_id: int | None
    municipio_codigo: str
    nombre: str
    sector_sgr: str
    subsector_sgr: str | None
    tipo_inversion: str | None
    fuente_sgr: str | None
    score_sgr: float | None
    elegible: bool | None
    razon_elegibilidad: str | None
    cuadrante: str | None
    en_plan: bool | None
    estado: str
    modo: str
    creado_en: datetime
    actualizado_en: datetime
    guardado_en: datetime | None = None
    resultado_duplicidad: dict[str, Any] | None = None
    validacion_costos: dict[str, Any] | None = None
    diagnostico_mga: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Ficha MGA ─────────────────────────────────────────────────────────────────

class GenerarFichaMGARequest(BaseModel):
    """Body opcional para POST /sgr/generar-ficha-mga/{proyecto_id}."""

    forzar_regeneracion: bool = Field(
        False,
        description="Si true, regenera la ficha aunque ya exista una guardada",
    )
    top_chunks_plan: int = Field(
        5,
        ge=1,
        le=20,
        description="Número de fragmentos del plan a incluir como contexto RAG",
    )


class FichaMGAOut(BaseModel):
    id: int
    proyecto_id: str
    identificacion: str | None
    preparacion: str | None
    evaluacion: str | None
    programacion: str | None
    campos_completos: int
    modelo_usado: str | None
    generado_en: datetime
    actualizado_en: datetime
    chat_historial: list[dict] = []

    model_config = ConfigDict(from_attributes=True)

    @field_validator("chat_historial", mode="before")
    @classmethod
    def _chat_historial_none_a_lista(cls, v: list[dict] | None) -> list[dict]:
        """La columna JSON en BD es NULLABLE; normaliza NULL a lista vacía."""
        return v or []


class ActualizarFichaMGARequest(BaseModel):
    """Body del PATCH /sgr/ficha-mga/{proyecto_id} — edición manual de secciones."""

    identificacion: str | None = None
    preparacion: str | None = None
    evaluacion: str | None = None
    programacion: str | None = None


class ChatFichaMGARequest(BaseModel):
    """Body del POST /sgr/ficha-mga/{proyecto_id}/chat."""

    mensaje: str = Field(..., min_length=2, max_length=2000)


class ChatFichaMGAResponse(BaseModel):
    """Respuesta del chat de edición conversacional sobre la Ficha MGA."""

    respuesta_ia: str
    ficha: FichaMGAOut


# ── Verificación de duplicidad ─────────────────────────────────────────────────

NivelDuplicidad = Literal["ALTO", "MEDIO", "BAJO"]


class SimilarRagItem(BaseModel):
    """Ítem del mapa de inversiones encontrado por búsqueda semántica."""

    texto: str
    nombre_proyecto: str
    codigo_bpin: str | None
    municipio: str
    score_qdrant: float


class VerificarDuplicidadResponse(BaseModel):
    """Respuesta del endpoint POST /sgr/verificar-duplicidad/{proyecto_id}."""

    proyecto_id: str
    nivel: NivelDuplicidad
    score_similitud: float = Field(..., ge=0.0, le=1.0)
    proyecto_similar: str | None
    codigo_bpin: str | None
    estado_similar: str | None
    recomendacion: str
    puede_continuar: bool
    bloqueado: bool = Field(
        False,
        description="True si nivel ALTO o score ≥ 0.85; impide avanzar en el flujo",
    )
    similares_rag: list[SimilarRagItem] = Field(default_factory=list)
    verificado_en: datetime = Field(default_factory=datetime.utcnow)


# ── Modo 2: Evaluación Inversa (M5) ───────────────────────────────────────────

class EvaluarProyectoRequest(BaseModel):
    """Body del POST /sgr/evaluar-proyecto."""

    texto_proyecto: str = Field(
        ...,
        min_length=50,
        description=(
            "Texto descriptivo del proyecto a evaluar: nombre, objeto, sector, "
            "justificación, valor estimado, fuente SGR propuesta. "
            "Puede pegarse el resumen ejecutivo de una ficha existente."
        ),
    )
    plan_id: str | None = Field(
        None,
        description="ID del plan de desarrollo para buscar chunks contextuales vía RAG",
    )
    proyecto_id: str | None = Field(
        None,
        description="Si ya existe como ProyectoSGR, su ID; se persiste el diagnóstico allí",
    )
    guardar: bool = Field(True, description="Persistir diagnóstico en ProyectoSGR.diagnostico_mga")
    top_chunks_plan: int = Field(6, ge=1, le=20)

    @field_validator("texto_proyecto")
    @classmethod
    def _val_max_chars(cls, v: str) -> str:
        from app.core.config import get_settings
        limite = get_settings().max_chars_texto_libre
        if len(v) > limite:
            raise ValueError(
                f"El texto excede el máximo permitido ({len(v)}/{limite} caracteres). "
                "Depura la información antes de enviarla (ej. usa un resumen tipo ficha EBI)."
            )
        return v


class DiagnosticoDimension(BaseModel):
    """Resultado de una dimensión del diagnóstico inverso."""

    nombre: str
    score: float = Field(..., ge=0.0, le=1.0)
    nivel: Literal["alto", "medio", "bajo"]
    hallazgos: list[str] = Field(default_factory=list)
    recomendaciones: list[str] = Field(default_factory=list)


class SubflujoInclusion(BaseModel):
    """Sub-flujo para incluir el proyecto en el Plan de Desarrollo via Concejo."""

    necesita_inclusion: bool
    checklist_concejo: list[str] = Field(default_factory=list)
    texto_acuerdo_sugerido: str | None = None


class EvaluarProyectoResponse(BaseModel):
    """Respuesta completa del Modo 2 — Evaluación Inversa."""

    # Dimensiones
    estructura_mga: DiagnosticoDimension
    alineacion_plan: DiagnosticoDimension
    analisis_estrategico: DiagnosticoDimension
    calificacion_sgr: DiagnosticoDimension

    # Score agregado y clasificación
    score_total: float = Field(..., ge=0.0, le=1.0)
    cuadrante: Literal["OPTIMO", "BIEN_JUSTIFICADO", "ATRACTIVO_CON_RIESGO", "REFORMULAR"]
    cuadrante_label: str
    semaforo: Literal["verde", "amarillo", "rojo"]
    semaforo_label: str

    # ¿Está en el plan?
    en_plan: bool
    evidencia_plan: str = ""

    # Sub-flujo inclusión
    subflujo_inclusion: SubflujoInclusion

    # Metadata
    proyecto_id: str | None = None
    plan_id: str | None = None
    procesado_en: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


# ── M6: Carga de matriz de proyectos SGR (seed de duplicidad) ─────────────────

EstadoSeedTarea = Literal["idle", "running", "completed", "cancelled", "error"]
FaseSeed = Literal["extrayendo", "leyendo_filas", "indexando"]


class DuplicidadSeedEstado(BaseModel):
    """Estado de la carga en background del Excel GESPROY/DNP de proyectos SGR."""

    estado: EstadoSeedTarea
    fase: FaseSeed | None = None
    iniciado_en: datetime | None = None
    finalizado_en: datetime | None = None
    filas_leidas: int = 0
    filas_filtradas: int = 0
    proyectos_indexados: int = 0
    proyectos_fallidos: int = 0
    error: str | None = None
