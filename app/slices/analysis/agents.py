"""
Agentes especializados de análisis.
Cada agente ejecuta búsquedas multi-query en el RAG y procesa el resultado con el LLM.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.slices.rag.ollama_client import OllamaError, ollama_chat
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

# ── Queries especializadas por agente ─────────────────────────────────────

AGENT_QUERIES: dict[str, list[str]] = {
    "responsabilidades": [
        "responsabilidades y competencias del municipio",
        "obligaciones de la alcaldía y secretarías",
        "funciones asignadas por nivel territorial",
        "metas y compromisos del plan de desarrollo",
    ],
    "leyes": [
        "leyes decretos resoluciones marco normativo",
        "Ley 715 competencias sector salud educación agua",
        "Constitución Política artículos organización territorial",
        "normativa vigente plan de desarrollo territorial",
    ],
    "actores": [
        "entidades instituciones actores responsables",
        "alcaldía gobernación ministerios secretarías",
        "organismos de control y seguimiento",
        "participación institucional plan de desarrollo",
    ],
    "brechas": [
        "responsabilidades sin asignar vacíos normativos",
        "conflicto competencias duplicidad responsabilidades",
        "incumplimiento normativo obligaciones pendientes",
        "sectores sin cobertura institucional",
    ],
}

# ── Prompts del sistema por agente ────────────────────────────────────────

JERARQUIA_JURIDICA = """
Jerarquía Jurídica Colombiana (orden de supremacía):
1. Constitución Política de Colombia (1991) — norma de normas
2. Leyes Orgánicas (Ley Orgánica de Ordenamiento Territorial, Ley 617/2000)
3. Leyes Estatutarias
4. Leyes Ordinarias — Ley 715/2001 (SGP), Ley 136/1994 (municipios), Ley 1454/2011 (LOOT), Ley 152/1994
5. Decretos Ley / Decretos con fuerza de ley
6. Decretos Reglamentarios
7. Resoluciones Ministeriales
8. Ordenanzas Departamentales
9. Acuerdos Municipales
10. Decretos Alcaldes / Gobernadores
11. Circulares Administrativas
Regla: Una norma inferior NO puede contradecir una superior.
"""

_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "prompts"


def _load_agent_prompt(agent_type: str) -> str:
    path = _PROMPTS_DIR / f"{agent_type}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _build_system_prompt(agent_type: str, nivel: str, depth: str) -> str:
    depth_instructions = {
        "basico": "Extrae las responsabilidades principales (máximo 10). No analices brechas complejas.",
        "estandar": "Extrae TODAS las responsabilidades mencionadas. Identifica todas las leyes citadas.",
        "profundo": "Extrae TODAS las responsabilidades, incluyendo las implícitas. Identifica brechas.",
    }
    return "\n\n".join(filter(None, [
        JERARQUIA_JURIDICA,
        f"Nivel territorial bajo análisis: {nivel}",
        depth_instructions.get(depth, depth_instructions["estandar"]),
        _load_agent_prompt(agent_type),
    ]))


# ── Multi-query RAG search ────────────────────────────────────────────────

async def search_multi_query(
    rag: RagService,
    queries: list[str],
    collection_id: str,
    top_k_per_query: int = 5,
) -> list[str]:
    """
    Ejecuta múltiples queries en paralelo, deduplica por texto y retorna
    los fragmentos de texto únicos re-rankeados por frecuencia+score.
    """
    thr = rag.settings.rag_default_score_threshold

    async def one_query(q: str):
        try:
            result = await rag.search(
                query=q,
                collection_ids=[collection_id],
                top_k=top_k_per_query,
                score_threshold=thr,
            )
            return result.chunks
        except Exception as exc:
            logger.warning("Error en query '%s': %s", q, exc)
            return []

    results = await asyncio.gather(*[one_query(q) for q in queries])

    # Deduplicar por chunk_id, acumular score y hits
    seen: dict[str, dict] = {}
    for chunks in results:
        for chunk in chunks:
            cid = chunk.chunk_id
            if cid not in seen:
                seen[cid] = {"text": chunk.text, "score": 0.0, "hits": 0}
            seen[cid]["score"] += chunk.score
            seen[cid]["hits"] += 1

    ranked = sorted(
        seen.values(),
        key=lambda x: (x["score"] / x["hits"]) * (1 + 0.2 * x["hits"]),
        reverse=True,
    )
    return [r["text"] for r in ranked[:15]]


# ── Helpers de parsing ────────────────────────────────────────────────────

def _parse_pipe_lines(text: str, n_fields: int) -> list[list[str]]:
    """Parsea líneas con formato: campo1 | campo2 | ... | campoN"""
    results: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip().lstrip("- ").strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= n_fields:
            results.append(parts)
    return results


def _parse_json_array(text: str) -> list[dict]:
    """Extrae el primer array JSON del texto."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


# ── Función de retry adaptada ─────────────────────────────────────────────

async def _llm_call_with_retry(
    http: httpx.AsyncClient,
    base_url: str,
    model: str,
    system: str,
    user: str,
    max_retries: int = 3,
    label: str = "",
) -> str:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await ollama_chat(
                http=http,
                base_url=base_url,
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except (OllamaError, httpx.TimeoutException, httpx.ConnectError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                wait = 2.0 ** attempt
                logger.warning("[%s] Reintento %d tras error: %s", label, attempt + 1, exc)
                await asyncio.sleep(wait)
    raise RuntimeError(f"[{label}] Falló tras {max_retries} intentos: {last_error}")


# ── Agentes especializados ────────────────────────────────────────────────

async def responsabilidades_agent(
    rag: RagService,
    collection_id: str,
    nivel: str,
    depth: str,
    extra_chunks: list[str] | None = None,
) -> list[dict[str, Any]]:
    chunks = await search_multi_query(rag, AGENT_QUERIES["responsabilidades"], collection_id)
    if extra_chunks:
        chunks = extra_chunks + chunks

    context = "\n\n---\n\n".join(chunks[:12])
    system = _build_system_prompt("responsabilidades", nivel, depth)
    user = (
        f"Analiza el siguiente texto de un plan de desarrollo y extrae TODAS las responsabilidades.\n\n"
        f"TEXTO:\n{context}\n\n"
        "Responde en formato: [TITULO] | [DESCRIPCION] | [TIPO:P/C/S/N] | [SECTOR] | [REF_LEGAL] | [OBLIGATORIEDAD]"
    )

    try:
        response = await _llm_call_with_retry(
            rag.http, rag.settings.ollama_base_url, rag.settings.ollama_chat_model,
            system, user, label="responsabilidades"
        )
    except RuntimeError as exc:
        logger.error("Agente responsabilidades falló: %s", exc)
        return []

    items = []
    for parts in _parse_pipe_lines(response, 2):
        tipo_raw = parts[2].strip().upper() if len(parts) > 2 else "P"
        tipo = tipo_raw if tipo_raw in ("P", "C", "S", "N") else "P"
        items.append({
            "titulo": parts[0],
            "descripcion": parts[1] if len(parts) > 1 else "",
            "tipo": tipo,
            "sector": parts[3] if len(parts) > 3 else "",
            "referencia_legal": parts[4] if len(parts) > 4 else None,
        })
    return items


async def leyes_agent(
    rag: RagService,
    collection_id: str,
    nivel: str,
    depth: str,
    extra_chunks: list[str] | None = None,
) -> list[dict[str, Any]]:
    chunks = await search_multi_query(rag, AGENT_QUERIES["leyes"], collection_id)
    if extra_chunks:
        chunks = extra_chunks + chunks

    context = "\n\n---\n\n".join(chunks[:12])
    system = _build_system_prompt("leyes", nivel, depth)
    user = (
        f"Identifica TODAS las leyes, decretos y normas en el siguiente texto.\n\n"
        f"TEXTO:\n{context}\n\n"
        "Responde en formato: [CODIGO] | [TITULO] | [TIPO] | [ARTICULOS] | [RELEVANCIA] | [VIGENTE:si/no] | [JERARQUIA:1-11]"
    )

    try:
        response = await _llm_call_with_retry(
            rag.http, rag.settings.ollama_base_url, rag.settings.ollama_chat_model,
            system, user, label="leyes"
        )
    except RuntimeError as exc:
        logger.error("Agente leyes falló: %s", exc)
        return []

    items = []
    for parts in _parse_pipe_lines(response, 2):
        tipo_raw = parts[2].strip().lower() if len(parts) > 2 else "ley"
        tipo = tipo_raw if tipo_raw in ("ley", "decreto", "resolucion", "circular") else "ley"
        items.append({
            "norma_codigo": parts[0],
            "titulo": parts[1] if len(parts) > 1 else parts[0],
            "tipo": tipo,
            "articulos": parts[3] if len(parts) > 3 else None,
            "extracto": parts[4] if len(parts) > 4 else None,
            "vigente": (parts[5].strip().lower() if len(parts) > 5 else "si") != "no",
        })
    return items


async def actores_agent(
    rag: RagService,
    collection_id: str,
    nivel: str,
    depth: str,
    extra_chunks: list[str] | None = None,
) -> list[dict[str, Any]]:
    chunks = await search_multi_query(rag, AGENT_QUERIES["actores"], collection_id)
    if extra_chunks:
        chunks = extra_chunks + chunks

    context = "\n\n---\n\n".join(chunks[:10])
    system = _build_system_prompt("actores", nivel, depth)
    user = (
        f"Identifica TODAS las entidades e instituciones con responsabilidades en el plan.\n\n"
        f"TEXTO:\n{context}\n\n"
        "Responde en formato: [NOMBRE] | [SIGLA] | [TIPO:principal/concurrente/subsidiario/otro] | [NIVEL] | [COMPETENCIAS]"
    )

    try:
        response = await _llm_call_with_retry(
            rag.http, rag.settings.ollama_base_url, rag.settings.ollama_chat_model,
            system, user, label="actores"
        )
    except RuntimeError as exc:
        logger.error("Agente actores falló: %s", exc)
        return []

    items = []
    for parts in _parse_pipe_lines(response, 1):
        tipo_raw = parts[2].strip().lower() if len(parts) > 2 else "otro"
        tipo = tipo_raw if tipo_raw in ("principal", "concurrente", "subsidiario", "otro") else "otro"
        items.append({
            "nombre": parts[0],
            "sigla": parts[1] if len(parts) > 1 else "",
            "tipo": tipo,
            "nivel": parts[3] if len(parts) > 3 else nivel,
            "competencias": parts[4] if len(parts) > 4 else "",
        })
    return items


async def brechas_agent(
    rag: RagService,
    collection_id: str,
    nivel: str,
    depth: str,
    extra_chunks: list[str] | None = None,
) -> list[dict[str, Any]]:
    chunks = await search_multi_query(rag, AGENT_QUERIES["brechas"], collection_id)
    if extra_chunks:
        chunks = extra_chunks + chunks

    context = "\n\n---\n\n".join(chunks[:10])
    system = _build_system_prompt("brechas", nivel, depth)
    user = (
        f"Identifica TODAS las brechas, déficits y problemas normativos en el plan.\n\n"
        f"TEXTO:\n{context}\n\n"
        "Responde en formato: [TITULO] | [DESCRIPCION] | [TIPO:critica/duplicidad/sin_responsable/indefinido] | "
        "[SEVERIDAD:alta/media/baja] | [NORMA_BASE] | [RECOMENDACION]"
    )

    try:
        response = await _llm_call_with_retry(
            rag.http, rag.settings.ollama_base_url, rag.settings.ollama_chat_model,
            system, user, label="brechas"
        )
    except RuntimeError as exc:
        logger.error("Agente brechas falló: %s", exc)
        return []

    items = []
    _tipo_map = {"omision_normativa": "indefinido", "alerta": "indefinido"}
    for parts in _parse_pipe_lines(response, 2):
        tipo_raw = parts[2].strip().lower() if len(parts) > 2 else "critica"
        tipo_raw = _tipo_map.get(tipo_raw, tipo_raw)
        tipo = tipo_raw if tipo_raw in ("critica", "duplicidad", "sin_responsable", "indefinido") else "critica"
        sev_raw = parts[3].strip().lower() if len(parts) > 3 else "media"
        severidad = sev_raw if sev_raw in ("alta", "media", "baja") else "media"
        items.append({
            "titulo": parts[0],
            "descripcion": parts[1] if len(parts) > 1 else "",
            "tipo": tipo,
            "severidad": severidad,
            "referencia_legal": parts[4] if len(parts) > 4 else None,
        })
    return items


async def matriz_agent(
    rag: RagService,
    collection_id: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    resp_summary = "\n".join(
        f"- {r['titulo']} ({r.get('sector', '')})"
        for r in context.get("responsabilidades", [])[:20]
    )
    leyes_summary = "\n".join(
        f"- {l['norma_codigo']}: {l['titulo']}"
        for l in context.get("leyes", [])[:10]
    )

    system = _load_agent_prompt("matriz") or (
        "Eres un experto en competencias territoriales colombianas. "
        "Construye una matriz de competencias. "
        "Responde ÚNICAMENTE con un array JSON válido. Sin texto adicional."
    )
    user = (
        "Construye la Matriz de Competencias Territoriales basándote en estas responsabilidades y leyes.\n\n"
        f"RESPONSABILIDADES:\n{resp_summary}\n\n"
        f"LEYES:\n{leyes_summary}\n\n"
        "Formato JSON exacto:\n"
        '[{"competencia":"...","ley_base":"...","nacion":"P|C|S|N","departamento":"P|C|S|N",'
        '"municipio":"P|C|S|N","especializado":"P|C|S|N","sector":"...","brecha":"ok|critica|duplicidad|indefinido"}]'
    )

    try:
        response = await _llm_call_with_retry(
            rag.http, rag.settings.ollama_base_url, rag.settings.ollama_chat_model,
            system, user, label="matriz"
        )
        return _parse_json_array(response)
    except RuntimeError as exc:
        logger.error("Agente matriz falló: %s", exc)
        return []


# ── Ejecutor paralelo de agentes ──────────────────────────────────────────

AGENT_DEPENDENCIES = {
    "matriz": ["responsabilidades", "leyes", "actores"],
    "brechas": ["responsabilidades"],
}


async def run_parallel_agents(
    agents: list[tuple[str, Any]],
    emit,
) -> dict[str, Any]:
    results: dict[str, Any] = {}

    async def run_one(name: str, fn) -> None:
        await emit({"type": "agent_start", "agent": name})
        try:
            result = await fn()
            results[name] = result or []
            await emit({"type": "agent_done", "agent": name, "count": len(results[name])})
        except Exception as exc:
            logger.exception("Agente '%s' falló", name)
            results[name] = []
            await emit({"type": "agent_error", "agent": name, "error": str(exc)})

    await asyncio.gather(*[run_one(name, fn) for name, fn in agents])

    for dep_agent, deps in AGENT_DEPENDENCIES.items():
        failed = [d for d in deps if not results.get(d)]
        if failed and dep_agent in dict(agents):
            await emit({
                "type": "warning",
                "msg": f"'{dep_agent}' ejecutará con contexto incompleto. Agentes sin resultados: {failed}",
            })

    return results
