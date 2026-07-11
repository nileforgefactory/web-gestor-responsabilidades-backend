"""Endpoints del slice SGR — Caja de Herramientas SGR Cat. 5 y 6."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.dependencies import get_rag_service
from app.slices.auth.dependencies import AdminUser, CurrentUser, get_current_user
from app.slices.sgr import duplicidad_seed_service
from app.slices.sgr.export_mga_docx import generar_docx_ficha
from app.slices.sgr.models import FichaMGA, ProyectoSGR
from app.slices.sgr.schemas import (
    ActualizarFichaMGARequest,
    ChatFichaMGARequest,
    ChatFichaMGAResponse,
    DuplicidadSeedEstado,
    EvaluarPlanResponse,
    EvaluarProyectoRequest,
    EvaluarProyectoResponse,
    FichaMGAOut,
    GenerarFichaMGARequest,
    ProyectoSGROut,
    VerificarDuplicidadResponse,
)
from app.slices.sgr.service import (
    actualizar_ficha_mga_service,
    chat_ficha_mga_service,
    evaluar_plan_sgr,
    evaluar_proyecto_service,
    generar_ficha_mga_service,
    guardar_proyecto_service,
    verificar_duplicidad_service,
)
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sgr",
    tags=["sgr"],
    dependencies=[Depends(get_current_user)],
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
    # MySQL no soporta NULLS LAST; en orden DESC ya ubica los NULL al final por defecto.
    stmt = stmt.order_by(ProyectoSGR.score_sgr.desc())

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


@router.post(
    "/proyecto/{proyecto_id}/guardar",
    response_model=ProyectoSGROut,
    summary="Guardar explícitamente un proyecto SGR",
    description=(
        "Marca el proyecto como guardado por el usuario (guardado_en). "
        "Lo protege de ser eliminado en una re-evaluación del plan (Modo 1) y "
        "confirma su persistencia en Modo 2 (evaluación inversa)."
    ),
    responses={404: {"description": "Proyecto no encontrado"}},
)
async def guardar_proyecto_endpoint(
    proyecto_id: str,
    db: AsyncSession = Depends(get_db),
) -> ProyectoSGROut:
    try:
        proyecto = await guardar_proyecto_service(proyecto_id=proyecto_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProyectoSGROut.model_validate(proyecto)


# ── M4: Generación de Ficha MGA ───────────────────────────────────────────────

@router.post(
    "/generar-ficha-mga/{proyecto_id}",
    response_model=FichaMGAOut,
    summary="M4 — Generar Ficha MGA Web para un proyecto SGR",
    description=(
        "Genera el contenido de las cuatro secciones de la MGA Web "
        "(Identificación, Preparación, Evaluación, Programación) "
        "para un proyecto SGR candidato usando el agente LLM + contexto RAG del plan.\n\n"
        "Si la ficha ya existe, retorna la guardada salvo que `forzar_regeneracion=true`. "
        "Al completar las 4 secciones, el proyecto avanza a estado `pre_validado`."
    ),
    responses={
        404: {"description": "Proyecto no encontrado"},
        503: {"description": "MySQL no configurado"},
    },
)
async def generar_ficha_mga(
    proyecto_id: str,
    body: GenerarFichaMGARequest = GenerarFichaMGARequest(),
    db: AsyncSession = Depends(get_db),
    rag: RagService = Depends(get_rag_service),
) -> FichaMGAOut:
    """Genera o recupera la Ficha MGA Web para el proyecto indicado."""
    settings = get_settings()
    try:
        ficha = await generar_ficha_mga_service(
            proyecto_id=proyecto_id,
            db=db,
            rag=rag,
            http=rag.http,
            settings=settings,
            forzar_regeneracion=body.forzar_regeneracion,
            top_chunks_plan=body.top_chunks_plan,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[generar_ficha_mga] Error proyecto=%s", proyecto_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FichaMGAOut.model_validate(ficha)


# ── M4b: Edición manual, chat conversacional y exportación Word ───────────────

@router.patch(
    "/ficha-mga/{proyecto_id}",
    response_model=FichaMGAOut,
    summary="Editar manualmente la Ficha MGA",
    description=(
        "Actualiza manualmente una o más secciones de la Ficha MGA "
        "(identificación, preparación, evaluación, programación). "
        "Solo se modifican los campos enviados en el body; los omitidos "
        "conservan su valor actual. Recalcula `campos_completos`."
    ),
    responses={404: {"description": "Ficha MGA no encontrada para el proyecto"}},
)
async def actualizar_ficha_mga_endpoint(
    proyecto_id: str,
    payload: ActualizarFichaMGARequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> FichaMGAOut:
    """Edita manualmente las secciones de la Ficha MGA de un proyecto."""
    try:
        return await actualizar_ficha_mga_service(
            proyecto_id=proyecto_id,
            payload=payload,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[actualizar_ficha_mga] Error proyecto=%s", proyecto_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/ficha-mga/{proyecto_id}/chat",
    response_model=ChatFichaMGAResponse,
    summary="Chat de edición conversacional sobre la Ficha MGA",
    description=(
        "Permite pedirle a la IA modificaciones conversacionales sobre la Ficha MGA "
        "completa (ej. 'amplía el cronograma', 'hazlo más específico en la población "
        "objetivo'). La IA decide qué sección(es) reescribir y devuelve una respuesta "
        "conversacional confirmando el cambio. El turno de usuario y de asistente "
        "quedan persistidos en `chat_historial`."
    ),
    responses={404: {"description": "Ficha MGA no encontrada para el proyecto"}},
)
async def chat_ficha_mga_endpoint(
    proyecto_id: str,
    payload: ChatFichaMGARequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    rag: RagService = Depends(get_rag_service),
) -> ChatFichaMGAResponse:
    """Chat conversacional para editar la Ficha MGA vía IA."""
    settings = get_settings()
    try:
        return await chat_ficha_mga_service(
            proyecto_id=proyecto_id,
            mensaje=payload.mensaje,
            db=db,
            http=rag.http,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[chat_ficha_mga] Error proyecto=%s", proyecto_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/ficha-mga/{proyecto_id}/export-docx",
    summary="Descargar la Ficha MGA como documento Word",
    description=(
        "Genera y descarga un documento Word (.docx) con las cuatro secciones "
        "de la Ficha MGA del proyecto indicado."
    ),
    responses={404: {"description": "Ficha MGA no encontrada para el proyecto"}},
)
async def exportar_ficha_mga_docx(
    proyecto_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exporta la Ficha MGA del proyecto como documento Word descargable."""
    result = await db.execute(select(ProyectoSGR).where(ProyectoSGR.id == proyecto_id))
    proyecto = result.scalar_one_or_none()
    if proyecto is None:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")

    ficha_result = await db.execute(select(FichaMGA).where(FichaMGA.proyecto_id == proyecto_id))
    ficha = ficha_result.scalar_one_or_none()
    if ficha is None:
        raise HTTPException(
            status_code=404, detail=f"Ficha MGA para proyecto '{proyecto_id}' no encontrada"
        )

    try:
        contenido = generar_docx_ficha(ficha=ficha, proyecto_nombre=proyecto.nombre)
    except Exception as exc:
        logger.exception("[exportar_ficha_mga_docx] Error proyecto=%s", proyecto_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="ficha_mga_{proyecto_id}.docx"'},
    )


# ── M3: Verificación de Duplicidad ────────────────────────────────────────────

@router.post(
    "/verificar-duplicidad/{proyecto_id}",
    response_model=VerificarDuplicidadResponse,
    summary="M3 — Verificar duplicidad de un proyecto SGR",
    description=(
        "Busca proyectos similares en la base de conocimiento (Qdrant) y evalúa "
        "el nivel de duplicidad vía LLM.\n\n"
        "**Umbrales:**\n"
        "- `ALTO` (score ≥ 0.85): bloquea la formulación — proyecto muy similar ya existe.\n"
        "- `MEDIO` (0.60–0.84): advertencia — revisar diferenciación.\n"
        "- `BAJO` (< 0.60): sin duplicidad detectada.\n\n"
        "El resultado queda persistido en `resultado_duplicidad` del proyecto."
    ),
    responses={
        404: {"description": "Proyecto no encontrado"},
        503: {"description": "MySQL no configurado"},
    },
)
async def verificar_duplicidad(
    proyecto_id: str,
    db: AsyncSession = Depends(get_db),
    rag: RagService = Depends(get_rag_service),
) -> VerificarDuplicidadResponse:
    """Verifica duplicidad del proyecto contra el Mapa de Inversiones SGR."""
    settings = get_settings()
    try:
        response = await verificar_duplicidad_service(
            proyecto_id=proyecto_id,
            db=db,
            rag=rag,
            http=rag.http,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[verificar_duplicidad] Error proyecto=%s", proyecto_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return response


# ── M5: Evaluación Inversa (Modo 2) ───────────────────────────────────────────

@router.post(
    "/evaluar-proyecto",
    response_model=EvaluarProyectoResponse,
    summary="M5 — Modo 2: evaluación inversa de un proyecto SGR existente",
    description=(
        "Diagnostica un proyecto de inversión ya formulado (o en formulación) "
        "evaluándolo en 4 dimensiones:\n\n"
        "- **Estructura MGA**: coherencia con las 4 secciones de la MGA Web\n"
        "- **Alineación Plan**: el proyecto resuelve un problema del Plan de Desarrollo\n"
        "- **Análisis Estratégico**: pertinencia, complementariedad y capacidad institucional\n"
        "- **Calificación SGR**: elegibilidad normativa y fuente correcta\n\n"
        "Clasifica el proyecto en uno de 4 cuadrantes:\n"
        "- `OPTIMO`: alta estructura + alta alineación → proceder\n"
        "- `BIEN_JUSTIFICADO`: baja estructura + alta alineación → reformular MGA\n"
        "- `ATRACTIVO_CON_RIESGO`: alta estructura + baja alineación → incluir en Plan primero\n"
        "- `REFORMULAR`: todo bajo → rediseñar\n\n"
        "Si el proyecto **no está en el Plan de Desarrollo**, genera automáticamente "
        "el texto del Acuerdo Municipal para presentar ante el Concejo."
    ),
    responses={
        422: {"description": "texto_proyecto demasiado corto (mínimo 50 caracteres)"},
        503: {"description": "MySQL no configurado"},
    },
)
async def evaluar_proyecto_endpoint(
    body: EvaluarProyectoRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    rag: RagService = Depends(get_rag_service),
) -> EvaluarProyectoResponse:
    """Modo 2 — diagnóstico inverso de un proyecto SGR con RAG bidireccional."""
    settings = get_settings()
    try:
        response = await evaluar_proyecto_service(
            texto_proyecto=body.texto_proyecto,
            plan_id=body.plan_id,
            proyecto_id=body.proyecto_id,
            db=db,
            rag=rag,
            http=rag.http,
            settings=settings,
            guardar=body.guardar,
            top_chunks_plan=body.top_chunks_plan,
        )
    except Exception as exc:
        logger.exception("[evaluar_proyecto] Error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return response


# ── M6: Carga de matriz de proyectos SGR (seed de duplicidad, solo admin) ─────

@router.post(
    "/duplicidad-seed/iniciar",
    response_model=DuplicidadSeedEstado,
    summary="Subir Excel GESPROY/DNP y (re)indexar proyectos SGR para duplicidad",
    description=(
        "Solo admin/superadmin. Sube el Excel 'Balance de Seguimiento a las "
        "Inversiones del SGR', filtra proyectos con al menos un municipio "
        "categoría 5/6 y los indexa en Qdrant en background. "
        "Si ya hay una carga en curso, retorna 409."
    ),
)
async def iniciar_duplicidad_seed(
    admin: AdminUser,
    file: UploadFile,
    settings: Settings = Depends(get_settings),
    rag: RagService = Depends(get_rag_service),
) -> DuplicidadSeedEstado:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un .xlsx")

    max_bytes = settings.duplicidad_seed_max_file_bytes
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp_path = Path(tmp.name)
    total = 0
    try:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Archivo excede el máximo permitido ({max_bytes // (1024*1024)} MiB).",
                )
            tmp.write(chunk)
    finally:
        tmp.close()

    iniciado = duplicidad_seed_service.start_duplicidad_seed(
        xlsx_path=tmp_path, rag=rag, delete_source_after=True,
    )
    if not iniciado:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(409, "Ya hay una carga de matriz SGR en curso. Use /duplicidad-seed/estado para consultarla.")
    return duplicidad_seed_service.get_estado()


@router.post(
    "/duplicidad-seed/cancelar",
    response_model=DuplicidadSeedEstado,
    summary="Cancelar carga de matriz SGR en curso",
)
async def cancelar_duplicidad_seed(admin: AdminUser) -> DuplicidadSeedEstado:
    cancelado = duplicidad_seed_service.cancel_task()
    if not cancelado:
        raise HTTPException(409, "No hay ninguna carga de matriz SGR en curso.")
    return duplicidad_seed_service.get_estado()


@router.get(
    "/duplicidad-seed/estado",
    response_model=DuplicidadSeedEstado,
    summary="Estado actual de la carga de matriz SGR",
)
async def estado_duplicidad_seed(admin: AdminUser) -> DuplicidadSeedEstado:
    return duplicidad_seed_service.get_estado()
