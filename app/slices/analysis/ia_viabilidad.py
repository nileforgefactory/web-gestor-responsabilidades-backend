"""Genera análisis de viabilidad presupuestal y fuentes de recursos usando IA."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat

logger = logging.getLogger(__name__)

_PROMPT_SISTEMA = """
Eres un asesor senior en gestión pública territorial, derecho administrativo y finanzas públicas en Colombia.
Tu objetivo es entregar una GUÍA PRÁCTICA y EXTENSA para un funcionario que no necesariamente domina el marco legal:
qué puede hacer, bajo qué norma, cómo conseguir recursos, cómo mejorar el plan, qué hacer cuando una
responsabilidad NO le corresponde a su entidad, y cómo mitigar las brechas detectadas.

Responde ÚNICAMENTE con un JSON válido. No escribas nada fuera del JSON. No uses markdown, no uses ```json.

El JSON debe tener exactamente esta estructura:
{
  "que_hacer": "Párrafo de 4-6 oraciones explicando, en lenguaje claro, qué acciones concretas debe implementar la entidad según sus responsabilidades",
  "contexto_legal": "Párrafo de 3-5 oraciones que explica el marco normativo que habilita y obliga estas acciones (cita leyes/decretos por su nombre legible, ej: Ley 715 de 2001), traducido a lenguaje sencillo",
  "presupuesto_estimado": "Párrafo estimando rangos de presupuesto requerido en pesos colombianos, mencionando los componentes principales",
  "nivel_suficiencia": "suficiente|insuficiente|parcial",
  "suficiencia": "Párrafo de 2-3 oraciones explicando si el presupuesto disponible alcanza, cuánto falta o sobra",
  "fuentes_recursos": [
    {
      "tipo": "monetario|físico|legal|técnico",
      "entidad": "Nombre de la entidad o fondo",
      "descripcion": "Cómo acceder a estos recursos: requisitos, condiciones, pasos y a qué oficina acudir"
    }
  ],
  "recomendaciones_mejora": [
    "Recomendación concreta y accionable para mejorar el plan (indicadores, metas, articulación, presupuesto). Sé específico y extenso."
  ],
  "competencias_no_propias": [
    {
      "competencia": "Nombre de la competencia o responsabilidad que NO recae principalmente en esta entidad",
      "responsable": "Nivel o entidad que sí es titular (ej: Nación - Ministerio de Salud, Departamento, CAR)",
      "como_gestionar": "Cómo debe la entidad gestionarla pese a no ser titular: cofinanciación, convenio interadministrativo, solicitud formal, contrato-plan, coordinación",
      "norma_o_formato": "Norma o instrumento formal que habilita esa gestión (ej: Ley 1454 de 2011 contrato-plan, convenio interadministrativo Ley 489 de 1998)"
    }
  ],
  "mitigacion_brechas": [
    {
      "brecha": "Título de la brecha detectada",
      "severidad": "alta|media|baja",
      "accion": "Acción concreta y paso a paso para mitigar o cerrar la brecha en el plan",
      "norma_base": "Norma que respalda la corrección (nombre legible)"
    }
  ]
}

Reglas:
- fuentes_recursos: incluye al menos 2-3 monetarias (SGP, SGR/regalías, cooperación, Findeter, Banco Agrario), 1-2 físicas, 1-2 legales y 1 técnica (DNP, ministerios).
- recomendaciones_mejora: mínimo 4 recomendaciones, extensas y específicas al plan.
- competencias_no_propias: deriva del cruce territorial (cuando el nivel de la entidad NO es el titular principal). Si todas recaen en la entidad, devuelve [].
- mitigacion_brechas: una entrada por cada brecha crítica o de severidad alta del análisis. Usa las recomendaciones ya provistas como base y amplíalas.
""".strip()


def _build_prompt(plan: dict[str, Any]) -> str:
    titulo   = plan.get("titulo", "Sin título")
    nivel    = plan.get("nivel", "municipal")
    entidad  = plan.get("entidad", "")
    periodo  = plan.get("periodo", "")
    desc     = (plan.get("descripcion") or "")[:600]

    resps = plan.get("responsabilidades") or []
    resp_txt = "\n".join(
        f"- {r.get('titulo','')} [sector: {r.get('sector','')}]"
        for r in resps[:20]
    )

    normas = plan.get("normas") or []
    normas_txt = "\n".join(
        f"- {n.get('norma_codigo','')} {n.get('titulo','')[:80]}"
        for n in normas[:10]
    )

    brechas = plan.get("brechas") or []
    brechas_relevantes = [
        b for b in brechas
        if b.get("tipo") in ("critica", "sin_responsable") or b.get("severidad") == "alta"
    ]
    brechas_txt = "\n".join(
        f"- {b.get('titulo','')} (tipo: {b.get('tipo','')}, severidad: {b.get('severidad','')})"
        f"{' | norma: ' + str(b.get('referencia_legal')) if b.get('referencia_legal') else ''}"
        f"{' | recomendación previa: ' + str(b.get('recomendacion'))[:160] if b.get('recomendacion') else ''}"
        for b in brechas_relevantes[:12]
    )

    # Competencias cuyo titular principal NO es el nivel de la entidad (cruce de la matriz)
    nivel_col = {"nacional": "nacion", "departamental": "departamento", "municipal": "municipio"}.get(nivel)
    matriz = plan.get("matriz") or []
    no_propias_txt = ""
    if nivel_col:
        no_propias = [
            m for m in matriz
            if m.get(nivel_col, "N") in ("N", "S") and any(
                m.get(c) == "P" for c in ("nacion", "departamento", "municipio", "especializado") if c != nivel_col
            )
        ]
        no_propias_txt = "\n".join(
            f"- {m.get('competencia','')} (titular: "
            + ", ".join(
                lbl for lbl, c in (("Nación","nacion"),("Departamento","departamento"),
                                   ("Municipio","municipio"),("Especializado","especializado"))
                if m.get(c) == "P"
            )
            + f") ley_base={m.get('ley_base','')}"
            for m in no_propias[:12]
        )

    sectores = list({r.get("sector","") for r in resps if r.get("sector")})

    return f"""Plan de desarrollo: {titulo}
Nivel territorial: {nivel}
Entidad: {entidad}
Periodo: {periodo}
Descripción ejecutiva: {desc}

Sectores identificados: {', '.join(sectores[:10]) or 'No especificados'}

Responsabilidades principales ({len(resps)} total):
{resp_txt or 'Sin responsabilidades identificadas'}

Marco normativo ({len(normas)} normas):
{normas_txt or 'Sin normas identificadas'}

Brechas a mitigar ({len(brechas_relevantes)} de {len(brechas)} total):
{brechas_txt or 'Sin brechas relevantes'}

Competencias cuyo titular principal NO es esta entidad (gestionar vía cofinanciación/convenio):
{no_propias_txt or 'Todas las competencias relevantes recaen en esta entidad'}

Con base en esta información, completa TODOS los campos del JSON:
1. Qué debe implementar concretamente esta entidad y bajo qué contexto legal.
2. Presupuesto requerido (rangos en pesos) y si una entidad de nivel {nivel} normalmente alcanza.
3. Fuentes de recursos monetarios, físicos, legales y técnicos disponibles.
4. Recomendaciones extensas para mejorar el plan.
5. Para cada competencia que NO recae en esta entidad: cómo gestionarla y bajo qué norma/formato.
6. Para cada brecha: cómo mitigarla paso a paso y con qué norma base."""


async def generar_analisis_viabilidad(
    *,
    plan: dict[str, Any],
    http: httpx.AsyncClient,
    settings: Settings,
) -> dict[str, Any]:
    """
    Llama al LLM para generar el análisis de viabilidad presupuestal y fuentes de recursos.
    Retorna un dict listo para pasar a _seccion_analisis_ia del PDF.
    """
    prompt = _build_prompt(plan)
    logger.info("[PDF_IA] Generando análisis de viabilidad para plan: %s", plan.get("titulo",""))

    try:
        raw = await ai_chat(
            http=http,
            settings=settings,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {"role": "user",   "content": prompt},
            ],
        )
    except Exception as exc:
        logger.warning("[PDF_IA] Error llamando LLM: %s", exc)
        return _fallback_analisis(plan)

    # Extraer JSON de la respuesta
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        logger.warning("[PDF_IA] LLM no devolvió JSON válido — usando fallback")
        return _fallback_analisis(plan)

    try:
        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            raise ValueError("No es dict")
        # Validar campos mínimos
        if "que_hacer" not in data:
            data["que_hacer"] = raw[:500]
        # Garantizar que las listas existan y sean del tipo correcto
        for key in ("fuentes_recursos", "recomendaciones_mejora", "competencias_no_propias", "mitigacion_brechas"):
            if not isinstance(data.get(key), list):
                data[key] = []
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("[PDF_IA] JSON inválido: %s — usando fallback", exc)
        return _fallback_analisis(plan)


def _fallback_analisis(plan: dict[str, Any]) -> dict[str, Any]:
    """Análisis mínimo si el LLM falla o no está disponible."""
    nivel = plan.get("nivel", "municipal")

    # Mitigación derivada de las brechas ya persistidas (usa su recomendación si existe)
    brechas = plan.get("brechas") or []
    mitigacion = [
        {
            "brecha": b.get("titulo", ""),
            "severidad": b.get("severidad", "media"),
            "accion": b.get("recomendacion")
            or "Revisar la obligación legal asociada, asignar actor responsable y definir metas e indicadores en el plan.",
            "norma_base": b.get("referencia_legal") or "Por determinar",
        }
        for b in brechas
        if b.get("tipo") in ("critica", "sin_responsable") or b.get("severidad") == "alta"
    ][:12]

    return {
        "que_hacer": (
            "La entidad debe ejecutar las responsabilidades identificadas en el plan de desarrollo, "
            "garantizando la implementación de los programas y proyectos según el marco normativo vigente. "
            "Se recomienda priorizar las competencias con brechas críticas identificadas en el análisis."
        ),
        "contexto_legal": (
            "El marco aplicable parte de la Constitución (art. 288, distribución de competencias), la "
            "Ley 1454 de 2011 (Ordenamiento Territorial) y la Ley 715 de 2001 (competencias y recursos del SGP), "
            "complementadas por la normativa sectorial específica de cada responsabilidad."
        ),
        "recomendaciones_mejora": [
            "Definir indicadores de resultado y producto medibles para cada responsabilidad de tipo Principal.",
            "Asignar formalmente, mediante acto administrativo, un responsable por cada competencia y brecha crítica.",
            "Incluir el presupuesto plurianual de inversiones articulado con las fuentes de recursos identificadas.",
            "Establecer convenios o instancias de coordinación para las competencias concurrentes con otros niveles.",
        ],
        "competencias_no_propias": [],
        "mitigacion_brechas": mitigacion,
        "presupuesto_estimado": (
            "El presupuesto requerido depende de la escala de los proyectos identificados. "
            "Se recomienda elaborar estudios de costos detallados para cada responsabilidad identificada."
        ),
        "nivel_suficiencia": "parcial",
        "suficiencia": (
            f"Para una entidad de nivel {nivel} en Colombia, el presupuesto disponible habitualmente "
            "cubre las funciones básicas pero requiere gestión adicional de recursos para proyectos de inversión. "
            "Se recomienda identificar fuentes de cofinanciación."
        ),
        "fuentes_recursos": [
            {
                "tipo": "monetario",
                "entidad": "Sistema General de Participaciones (SGP)",
                "descripcion": "Transferencias del nivel central para educación, salud, agua potable y propósito general. Acceso automático según distribución del DNP.",
            },
            {
                "tipo": "monetario",
                "entidad": "Sistema General de Regalías (SGR)",
                "descripcion": "Para municipios con producción minero-energética o fondos de compensación. Requiere proyecto de inversión aprobado por OCAD.",
            },
            {
                "tipo": "monetario",
                "entidad": "Cooperación Internacional",
                "descripcion": "APC-Colombia gestiona cooperación técnica y financiera no reembolsable. Requiere alineación con prioridades nacionales.",
            },
            {
                "tipo": "legal",
                "entidad": "Ley 1454 de 2011 — LOOT",
                "descripcion": "Marco legal para contratos-plan y convenios interadministrativos que permiten cofinanciar con la nación y el departamento.",
            },
            {
                "tipo": "técnico",
                "entidad": "Departamento Nacional de Planeación (DNP)",
                "descripcion": "Asistencia técnica gratuita para formulación de proyectos, gestión presupuestal y evaluación de políticas públicas.",
            },
        ],
    }
