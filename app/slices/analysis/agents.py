from __future__ import annotations

import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

from app.core.config import Settings
from app.slices.analysis import parsers
from app.slices.analysis.prompt_builder import build_agent_prompt
from app.slices.analysis.rag_context import (
    chunks_to_context_blob,
    fetch_agent_chunks,
    fetch_normativa_chunks,
    fetch_plan_chunks,
)
from app.slices.rag.ai_client import ai_chat
from app.slices.rag.service import RagService, _with_retries

# http y settings se mantienen en la firma de run_matriz_agent por compatibilidad con el caller

PARSER_BY_AGENT: dict[str, Callable[[str], list[dict[str, Any]]]] = {
    "responsabilidades": parsers.parse_responsabilidades,
    "leyes": parsers.parse_leyes,
    "actores": parsers.parse_actores,
    "brechas": parsers.parse_brechas,
}


async def run_agent(
    *,
    rag: RagService,
    http: httpx.AsyncClient,
    settings: Settings,
    agent: str,
    collection_ids: list[str],
    nivel: str,
    profundidad: str,
    entidad: str = "",
    extra_query: str | None = None,
    plan_excerpt: str = "",
    # Nuevos parámetros para análisis mejorado
    plan_collection_id: str | None = None,
    plan_doc_id: str | None = None,
    plan_text: str = "",
    normativa_collection_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Ejecuta un agente especializado con contexto RAG dual:
    - Chunks relevantes del PLAN (filtrados por document_id, con queries dinámicas)
    - Chunks de NORMATIVA (leyes, decretos de la base de conocimiento)

    Returns:
        Lista de dicts con campos del agente y ``chunk_ids`` / ``confidence_score``.
    """
    logger.info("[AGENT:%s] Iniciando — nivel=%s profundidad=%s extra_query=%r", agent, nivel, profundidad, extra_query)

    # ── Contexto del plan: chunks relevantes del documento indexado ───────────
    # La profundidad de lectura es configurable (settings.analysis_plan_top_k): con
    # modelos de contexto amplio se sube para no perder datos dispersos en el plan.
    plan_top_k = int(getattr(settings, "analysis_plan_top_k", 20))
    norm_top_k = int(getattr(settings, "analysis_normativa_top_k", 8))
    plan_chunks = []
    if plan_collection_id and plan_doc_id and plan_text:
        plan_chunks = await fetch_plan_chunks(
            rag,
            plan_collection_id=plan_collection_id,
            doc_id=plan_doc_id,
            agent=agent,
            plan_text=plan_text,
            top_k=plan_top_k,
            nivel=nivel,
        )
        logger.info("[AGENT:%s] Plan chunks: %d", agent, len(plan_chunks))

    # ── Contexto normativo: leyes/decretos de la base de conocimiento ─────────
    norm_ids = normativa_collection_ids or [c for c in collection_ids if c != plan_collection_id]
    if not norm_ids:
        norm_ids = collection_ids
    normativa_chunks = await fetch_normativa_chunks(
        rag,
        normativa_collection_ids=norm_ids,
        agent=agent,
        extra_query=extra_query,
        top_k=norm_top_k,
        nivel=nivel,
    )
    logger.info("[AGENT:%s] Normativa chunks: %d", agent, len(normativa_chunks))

    all_chunks = plan_chunks + normativa_chunks
    chunk_ids = [c.chunk_id for c in all_chunks]

    if not all_chunks:
        logger.warning("[AGENT:%s] ⚠ Sin chunks — el modelo recibirá contexto vacío", agent)

    system = build_agent_prompt(agent, nivel=nivel, profundidad=profundidad, entidad=entidad)
    user_parts: list[str] = []

    # Sección 1: contenido del plan (chunks relevantes). El tope es configurable.
    plan_blob_chars = int(getattr(settings, "analysis_plan_blob_chars", 16000))
    norm_blob_chars = int(getattr(settings, "analysis_normativa_blob_chars", 4000))
    if plan_chunks:
        blob = chunks_to_context_blob(plan_chunks)[:plan_blob_chars]
        user_parts.append(f"=== CONTENIDO DEL PLAN ===\n{blob}")
    elif plan_excerpt:
        user_parts.append(f"=== FRAGMENTO DEL PLAN ===\n{plan_excerpt[:plan_blob_chars]}")

    # Sección 2: normativa de respaldo
    if normativa_chunks:
        blob_norm = chunks_to_context_blob(normativa_chunks)[:norm_blob_chars]
        user_parts.append(f"=== NORMATIVA ===\n{blob_norm}")
    elif not plan_chunks:
        user_parts.append("No se encontró contexto relevante en la base de conocimiento.")

    user_parts.append("Extrae según el formato indicado en el system prompt.")

    async def call() -> str:
        return await ai_chat(
            http=http,
            settings=settings,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n".join(user_parts)},
            ],
        )

    raw = await _with_retries(call, attempts=3)
    parser = PARSER_BY_AGENT.get(agent)
    if not parser:
        return []
    items = parser(raw)
    logger.info("[AGENT:%s] Parser extrajo %d items de la respuesta del LLM", agent, len(items))
    if not items:
        logger.warning("[AGENT:%s] ⚠ Parser devolvió 0 items — respuesta cruda (500 chars): %s", agent, raw[:500])
    for item in items:
        item["chunk_ids"] = chunk_ids
        item["confidence_score"] = (
            sum(c.score for c in all_chunks) / len(all_chunks) if all_chunks else 0.0
        )
    return items


# Tipos jurídicos de brecha (prompt nuevo) → enum de la matriz (ok/critica/duplicidad/indefinido)
_BRECHA_DISPLAY_MAP = {
    "riesgo_disciplinario": "critica",
    "duplicidad_ilegal":    "duplicidad",
    "vacio_competencia":    "critica",
    "desarmonizacion":      "indefinido",
    "critica":              "critica",
    "duplicidad":           "duplicidad",
    "indefinido":           "indefinido",
    "sin_responsable":      "critica",
    "ok":                   "ok",
}

# Naturaleza de la competencia (prompt nuevo E/C/S/M) → celda territorial P/C/S/N
_RESP_TIPO_MATRIZ = {"E": "P", "C": "C", "S": "S", "M": "C", "P": "P", "N": "N"}


def build_matriz(context: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Construye la matriz de competencias territoriales cruzando responsabilidades,
    actores y leyes mediante la llave relacional ``id_norma`` (snake_case):
    cada fila incluye qué actores ejecutan la responsabilidad y qué leyes la
    fundamentan, con trazabilidad al fragmento del plan (``origen_contexto``).
    """
    responsabilidades: list[dict[str, Any]] = context.get("responsabilidades", [])
    actores: list[dict[str, Any]] = context.get("actores", [])
    leyes: list[dict[str, Any]] = context.get("leyes", [])
    brechas_ctx: list[dict[str, Any]] = context.get("brechas", [])

    # Índice de brechas por título normalizado (valor = enum de matriz ya mapeado)
    brechas_index: dict[str, str] = {
        str(b.get("titulo", "")).lower()[:40]: _BRECHA_DISPLAY_MAP.get(
            str(b.get("tipo", "ok")).lower(), "critica"
        )
        for b in brechas_ctx
    }
    # Índice de brechas por id_norma_base → enum de matriz (cruce relacional)
    brechas_por_norma: dict[str, str] = {}
    for b in brechas_ctx:
        nid = str(b.get("id_norma_base") or b.get("norma_base") or "").strip().lower()
        if nid:
            brechas_por_norma[nid] = _BRECHA_DISPLAY_MAP.get(
                str(b.get("tipo", "ok")).lower(), "critica"
            )

    # Índice de actores: nombre_lower → actor dict
    actor_by_name: dict[str, dict[str, Any]] = {
        str(a.get("nombre", "")).lower(): a for a in actores
    }

    # Índice de niveles presentes
    niveles_presentes: set[str] = {
        str(a.get("nivel", "municipal")) for a in actores
    }

    # Índice de leyes por id_norma (cruce relacional) y por código (fallback)
    ley_by_id_norma: dict[str, dict[str, Any]] = {
        str(l.get("id_norma", "")).strip().lower(): l
        for l in leyes
        if l.get("id_norma")
    }
    ley_by_codigo: dict[str, dict[str, Any]] = {
        str(l.get("codigo", "")).lower()[:40]: l for l in leyes
    }

    def _tipo(resp_tipo: str, nivel_actor: str, niveles: set[str]) -> str:
        t = _RESP_TIPO_MATRIZ.get(str(resp_tipo).upper()[:1], "P")
        if t == "C":
            return "C"
        if len(niveles) > 1 and t == "P":
            return "C"
        return t

    def _brecha(resp: dict[str, Any], nivel_count: int) -> str:
        # 1) cruce relacional por id_norma_ref ↔ id_norma_base de las brechas
        nid = str(resp.get("id_norma_ref") or resp.get("referencia_legal") or "").strip().lower()
        if nid and nid in brechas_por_norma:
            return brechas_por_norma[nid]
        # 2) cruce por título
        titulo_key = str(resp.get("titulo", "")).lower()[:40]
        if titulo_key in brechas_index:
            return brechas_index[titulo_key]
        # 3) heurística por cobertura territorial
        if nivel_count == 0:
            return "critica"
        if nivel_count > 1 and _RESP_TIPO_MATRIZ.get(str(resp.get("tipo", "P")).upper()[:1], "P") == "P":
            return "duplicidad"
        return "ok"

    def _actores_para_resp(resp: dict[str, Any]) -> list[dict[str, Any]]:
        """Actores que tienen competencias relacionadas con esta responsabilidad."""
        sector_resp = str(resp.get("sector", "")).lower()
        ref_legal = str(resp.get("referencia_legal", "")).lower()
        matched: list[dict[str, Any]] = []
        for actor in actores:
            competencias = str(actor.get("competencias", "")).lower()
            sector_actor = str(actor.get("sector", "")).lower()
            if sector_resp and sector_resp in competencias:
                matched.append(actor)
            elif ref_legal and ref_legal[:20] in competencias:
                matched.append(actor)
            elif sector_resp and sector_resp == sector_actor:
                matched.append(actor)
        return matched

    def _leyes_para_resp(resp: dict[str, Any]) -> list[dict[str, Any]]:
        """Leyes relacionadas con esta responsabilidad (cruce relacional por id_norma)."""
        nid = str(resp.get("id_norma_ref") or resp.get("referencia_legal") or "").strip().lower()
        # 1) match exacto por llave relacional id_norma
        if nid and nid in ley_by_id_norma:
            matched: list[dict[str, Any]] = [ley_by_id_norma[nid]]
        else:
            matched = []
        # 2) complementar por sector (sin duplicar)
        sector_resp = str(resp.get("sector", "")).lower()
        ya = {id(m) for m in matched}
        for ley in leyes:
            if id(ley) in ya:
                continue
            relevancia = str(ley.get("relevancia", "")).lower()
            if sector_resp and sector_resp in relevancia:
                matched.append(ley)
        return matched[:5]

    matriz: list[dict[str, Any]] = []
    seen: set[str] = set()
    nivel_mapa = {
        "nacional": "nacion",
        "regional": "especializado",      # CARs y entidades descentralizadas regionales
        "departamental": "departamento",
        "municipal": "municipio",
        "especializado": "especializado",
    }
    _SECTORES_PROHIBIDOS = {"", "general", "varios", "n/a", "na", "otro", "otros"}

    def _sector_valido(s: str) -> str:
        """Veto al sector 'general'/vacío: se exige un sector técnico DNP-KPT."""
        s = (s or "").strip()
        return "fortalecimiento_institucional" if s.lower() in _SECTORES_PROHIBIDOS else s

    def _col_para_nivel(nivel: str, celda: str) -> dict[str, str]:
        col = {"nacion": "N", "departamento": "N", "municipio": "N", "especializado": "N"}
        col[nivel_mapa.get(nivel, "municipio")] = celda
        return col

    def _emit(
        *, competencia: str, actor_nombre: str, col: dict[str, str], sector: str,
        ley_base: str, brecha: str, origen: str,
        actor_obj: dict[str, Any] | None, leyes_vinculadas: list[dict[str, Any]],
    ) -> None:
        matriz.append({
            "competencia":       competencia,
            "actor":             actor_nombre,
            "ley_base":          ley_base,
            "nacion":            col["nacion"],
            "departamento":      col["departamento"],
            "municipio":         col["municipio"],
            "especializado":     col["especializado"],
            "sector":            sector,
            "brecha":            brecha,
            "origen_contexto":   origen or "",
            "actores_vinculados": (
                [{"nombre": actor_obj.get("nombre", ""), "nivel": actor_obj.get("nivel", ""),
                  "tipo": actor_obj.get("tipo", "")}]
                if actor_obj else []
            ),
            "leyes_vinculadas":  leyes_vinculadas,
        })

    for resp in responsabilidades:
        titulo = str(resp.get("titulo", "")).strip()
        if not titulo:
            continue
        key = titulo.lower()[:50]
        if key in seen:
            continue
        seen.add(key)

        sector    = _sector_valido(str(resp.get("sector", "")))
        ley_base  = str(resp.get("id_norma_ref") or resp.get("referencia_legal") or "").strip()
        resp_tipo = str(resp.get("tipo", "P")).upper()[:1]
        origen    = resp.get("origen_contexto") or ""

        actores_vinculados = _actores_para_resp(resp)
        leyes_vinculadas = [
            {"codigo": l.get("codigo", ""), "titulo": l.get("titulo", "")}
            for l in _leyes_para_resp(resp)
        ]
        base_brecha = _brecha(resp, len(actores_vinculados))

        if actores_vinculados:
            # Regla de multiplicación: una fila por actor. Si hay >1 actor sobre la
            # misma competencia ⇒ duplicidad de competencias.
            duplicidad = len(actores_vinculados) > 1
            for actor in actores_vinculados:
                nivel_actor = str(actor.get("nivel", "municipal"))
                celda = _tipo(resp_tipo, nivel_actor, niveles_presentes)
                _emit(
                    competencia=titulo,
                    actor_nombre=str(actor.get("nombre", "")).strip(),
                    col=_col_para_nivel(nivel_actor, celda),
                    sector=sector,
                    ley_base=ley_base,
                    brecha="duplicidad" if duplicidad else base_brecha,
                    origen=origen,
                    actor_obj=actor,
                    leyes_vinculadas=leyes_vinculadas,
                )
        else:
            # Sin actor identificado: una fila con actor vacío (brecha de responsable).
            col = {"nacion": "N", "departamento": "N", "municipio": "N", "especializado": "N"}
            for nivel_actor, col_key in nivel_mapa.items():
                if nivel_actor in niveles_presentes:
                    col[col_key] = _tipo(resp_tipo, nivel_actor, niveles_presentes)
            if all(v == "N" for v in col.values()):
                col["municipio"] = "P"
            _emit(
                competencia=titulo, actor_nombre="", col=col, sector=sector,
                ley_base=ley_base, brecha=base_brecha, origen=origen,
                actor_obj=None, leyes_vinculadas=leyes_vinculadas,
            )

    # Actores sin responsabilidad vinculada: fila propia (brecha indefinida)
    actores_en_matriz = {str(r.get("actor", "")).lower() for r in matriz if r.get("actor")}
    for actor in actores:
        nombre = str(actor.get("nombre", "")).strip()
        if not nombre or nombre.lower() in actores_en_matriz:
            continue
        nivel_actor = str(actor.get("nivel", "municipal"))
        leyes_actor = [
            {"codigo": l.get("codigo", ""), "titulo": l.get("titulo", "")}
            for l in leyes
            if nombre.lower()[:15] in str(l.get("relevancia", "")).lower()
        ][:3]
        _emit(
            competencia=f"Competencias: {nombre}",
            actor_nombre=nombre,
            col=_col_para_nivel(nivel_actor, "P"),
            sector=_sector_valido(str(actor.get("sector", ""))),
            ley_base="",
            brecha="indefinido",
            origen=actor.get("origen_contexto") or "",
            actor_obj=actor,
            leyes_vinculadas=leyes_actor,
        )

    return matriz


def _build_super_contexto(context: dict[str, Any], plan_excerpt: str) -> str:
    """Empaqueta los hallazgos de los agentes 1-4 + el texto del plan para el Agente 5 LLM."""
    leyes = "\n".join(
        f"{l.get('id_norma','')} | {l.get('codigo','')} | {l.get('titulo','')}"
        for l in context.get("leyes", [])[:40]
    )
    resp = "\n".join(
        f"- {r.get('titulo','')} [{r.get('tipo','')}] sector={r.get('sector','')} "
        f"ley={r.get('id_norma_ref') or r.get('referencia_legal','')} | {r.get('origen_contexto','')}"
        for r in context.get("responsabilidades", [])[:60]
    )
    actores = "\n".join(
        f"- {a.get('nombre','')} | {a.get('tipo','')} | nivel={a.get('nivel','')} | {a.get('competencias','')}"
        for a in context.get("actores", [])[:40]
    )
    brechas = "\n".join(
        f"- {b.get('titulo','')} | {b.get('tipo','')} | sev={b.get('severidad','')} | "
        f"ley={b.get('id_norma_base') or b.get('norma_base','')}"
        for b in context.get("brechas", [])[:40]
    )
    return (
        "=== RESULTADOS DEL ANÁLISIS PREVIO ===\n\n"
        f"[NORMAS LEGALES IDENTIFICADAS]\n{leyes or 'Ninguna'}\n\n"
        f"[RESPONSABILIDADES Y COMPETENCIAS DETECTADAS]\n{resp or 'Ninguna'}\n\n"
        f"[ACTORES INSTITUCIONALES REGISTRADOS]\n{actores or 'Ninguno'}\n\n"
        f"[BRECHAS Y RIESGOS DETECTADOS EN EL PLAN]\n{brechas or 'Ninguna'}\n\n"
        f"=== TEXTO ORIGINAL DEL PLAN ANALIZADO ===\n{plan_excerpt[:6000]}\n\n"
        "Construye la matriz cruzando ÚNICAMENTE los datos anteriores. "
        "No inventes normas, sectores ni actores que no aparezcan arriba."
    )


async def run_matriz_agent(
    *,
    http: httpx.AsyncClient,
    settings: Settings,
    context: dict[str, Any],
    nivel: str,
    profundidad: str,
    plan_excerpt: str = "",
) -> list[dict[str, Any]]:
    """
    Construye la matriz de competencias.

    Modo (settings.analysis_matriz_mode):
      - "deterministic" (default): cruce relacional en Python por id_norma.
      - "llm": Agente 5 consolida un super-contexto y emite JSON saneado.
        Cae al modo determinista si el LLM falla o no devuelve JSON válido.
    """
    mode = getattr(settings, "analysis_matriz_mode", "deterministic")
    if mode != "llm":
        return build_matriz(context)

    system = build_agent_prompt("matriz", nivel=nivel, profundidad=profundidad)
    super_ctx = _build_super_contexto(context, plan_excerpt)

    async def call() -> str:
        return await ai_chat(
            http=http,
            settings=settings,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": super_ctx},
            ],
        )

    try:
        raw = await _with_retries(call, attempts=2)
    except Exception as exc:
        logger.warning("[MATRIZ:LLM] falló (%s) — usando matriz determinista", exc)
        return build_matriz(context)

    rows = parsers.limpiar_y_validar_matriz(raw)
    if not rows:
        logger.warning("[MATRIZ:LLM] JSON inválido o vacío — usando matriz determinista")
        return build_matriz(context)
    logger.info("[MATRIZ:LLM] %d filas saneadas", len(rows))
    return rows
