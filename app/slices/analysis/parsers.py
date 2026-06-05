"""Parseo de salidas estructuradas de agentes LLM."""

from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_pipe_line(line: str) -> list[str]:
    return [p.strip() for p in line.split("|")]


def _clean_line(raw: str) -> str:
    """Elimina prefijos de lista (-, *, 1., **) y espacios."""
    line = raw.strip()
    line = re.sub(r"^\*\*.*?\*\*\s*", "", line)   # **Título:**
    line = re.sub(r"^\d+\.\s*", "", line)          # 1.
    line = re.sub(r"^[-*]\s*", "", line)           # - o *
    return line.strip()


def _extract_section(text: str, *keywords: str) -> list[str]:
    """
    Extrae las líneas de lista bajo el primer encabezado que contenga alguna
    de las keywords (case-insensitive). Para cuando el modelo responde en
    markdown libre con secciones tipo **Leyes citadas:** o ## Actores.
    """
    lines = text.splitlines()
    collecting = False
    items: list[str] = []

    header_re = re.compile(
        r"(?:^#{1,3}\s*|^\*\*|^)(.+?)(?:\*\*)?:?\s*$",
        re.IGNORECASE,
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if collecting:
                # línea vacía no corta la sección, puede haber más items
                continue
            continue

        m = header_re.match(stripped)
        if m:
            heading = m.group(1).lower()
            if any(kw.lower() in heading for kw in keywords):
                collecting = True
                continue
            elif collecting:
                # nuevo encabezado → fin de sección
                break

        if collecting and re.match(r"^[\d\-\*]", stripped):
            cleaned = _clean_line(stripped)
            if cleaned:
                items.append(cleaned)

    return items


# ---------------------------------------------------------------------------
# Parsers primarios (pipe-separated)
# ---------------------------------------------------------------------------

def _parse_pipe_responsabilidades(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = _clean_line(raw)
        if "|" not in line or len(line) < 8:
            continue
        parts = _split_pipe_line(line)
        if len(parts) < 2:
            continue
        titulo = parts[0].strip()
        # Descartar líneas que sean nombres de actores o leyes, no acciones
        if _TITULO_ES_ACTOR_O_LEY_RE.match(titulo):
            continue
        out.append({
            "titulo": titulo,
            "descripcion": parts[1] if len(parts) > 1 else "",
            "tipo": parts[2] if len(parts) > 2 else "P",
            "sector": parts[3] if len(parts) > 3 else "",
            "referencia_legal": parts[4] if len(parts) > 4 else None,
            "obligatoriedad": parts[5] if len(parts) > 5 else None,
        })
    return out


def _parse_pipe_leyes(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = _clean_line(raw)
        if "|" not in line:
            continue
        parts = _split_pipe_line(line)
        if len(parts) < 2:
            continue
        out.append({
            "codigo": parts[0],
            "titulo": parts[1],
            "tipo": parts[2] if len(parts) > 2 else "ley",
            "articulos": parts[3] if len(parts) > 3 else "",
            "relevancia": parts[4] if len(parts) > 4 else "",
            "vigente": parts[5] if len(parts) > 5 else "si",
            "jerarquia": parts[6] if len(parts) > 6 else "",
        })
    return out


_NOMBRE_LARGO_RE = re.compile(r"^.{81,}")  # nombres > 80 chars → descripción, no actor
_NOMBRE_ORACION_RE = re.compile(
    r"^(competencias?:|el\s|la\s|los\s|las\s|se\s|que\s|para\s)",
    re.IGNORECASE,
)


def _parse_pipe_actores(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = _clean_line(raw)
        if "|" not in line:
            continue
        parts = _split_pipe_line(line)
        if len(parts) < 2:
            continue
        nombre = parts[0].strip()
        # Descartar si es una norma, una oración larga, o empieza como frase
        if _NOMBRE_ES_NORMA_RE.match(nombre):
            continue
        if _NOMBRE_LARGO_RE.match(nombre):
            continue
        if _NOMBRE_ORACION_RE.match(nombre):
            continue
        nivel_raw = (parts[3] if len(parts) > 3 else "").strip().lower()
        out.append({
            "nombre": nombre,
            "sigla": parts[1] if len(parts) > 1 else "",
            "tipo": parts[2] if len(parts) > 2 else "ejecutor",
            "nivel": nivel_raw if nivel_raw in ("nacional", "departamental", "municipal", "especializado") else "municipal",
            "competencias": parts[4] if len(parts) > 4 else "",
        })
    return out


def _parse_pipe_brechas(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = _clean_line(raw)
        if "|" not in line:
            continue
        parts = _split_pipe_line(line)
        if len(parts) < 2:
            continue
        out.append({
            "titulo": parts[0],
            "descripcion": parts[1],
            "tipo": parts[2] if len(parts) > 2 else "alerta",
            "severidad": parts[3] if len(parts) > 3 else "media",
            "norma_base": parts[4] if len(parts) > 4 else None,
            "recomendacion": parts[5] if len(parts) > 5 else None,
        })
    return out


# ---------------------------------------------------------------------------
# Fallbacks para respuesta markdown libre (modelos pequeños como llama3.1:8b)
# ---------------------------------------------------------------------------

_LEY_RE = re.compile(
    r"(constituc\w*|ley\s+\d[\d\s/de]*|decreto\s+\d[\d\s/de]*"
    r"|resoluci[oó]n\s+\d[\d\s/de]*|ordenanza|acuerdo\s+\d[\d\s/de]*"
    r"|plan\s+territorial|conpes\s+\d+)",
    re.IGNORECASE,
)

_SIGLA_RE = re.compile(r"\(([A-Z]{2,8})\)")

# Patrones que indican que el nombre de un "actor" es en realidad una ley/norma
_NOMBRE_ES_NORMA_RE = re.compile(
    r"^(?:"
    r"ley\s+\d|decreto\s+\d|resoluci[oó]n\s+\d|constituci[oó]n"
    r"|art[íi]culo\s+\d|cap[íi]tulo\s+\d|ordenanza|acuerdo\s+\d|conpes\s+\d"
    r"|circular\s+\d|directiva\s+\d|decreto\s+ley|decreto\s+legislativo"
    r"|pol[íi]tica\s+p[úu]blica|plan\s+nacional|plan\s+de\s+desarrollo"
    r")",
    re.IGNORECASE,
)

# Patrones que indican que una línea es un actor o ley, NO una responsabilidad
_TITULO_ES_ACTOR_O_LEY_RE = re.compile(
    r"^(?:"
    r"ley\s+\d|decreto\s+\d|resoluci[oó]n\s+\d|constituci[oó]n|ordenanza|acuerdo\s+\d|conpes\s+\d"  # leyes
    r"|alcald[íi]|concejo|gobernaci[oó]n|ministerio|secretar[íi]a|contralor[íi]a|procuradur[íi]a"    # actores comunes
    r"|corporaci[oó]n\s+aut[oó]noma|icbf|sena|dane|dnp|invias|ins\b|supersalud"                      # entidades
    r")",
    re.IGNORECASE,
)

_NIVEL_KEYWORDS = {
    "nacional": ["ministerio", "dane", "dnp", "icbf", "sena", "invias", "ins", "supersalud"],
    "departamental": ["gobernaci", "secretar.*dptal", "secretar.*departament", "corporaci.*regional", "cra"],
    "municipal": ["alcald", "concejo", "secretar.*municipal", "personero", "contralor"],
}


def _guess_nivel(nombre: str) -> str:
    n = nombre.lower()
    for nivel, kws in _NIVEL_KEYWORDS.items():
        if any(re.search(kw, n) for kw in kws):
            return nivel
    return "municipal"


def _guess_tipo_ley(codigo: str) -> str:
    c = codigo.lower()
    if "constituci" in c:
        return "constitucion"
    if "decreto" in c:
        return "decreto"
    if "resoluci" in c:
        return "resolucion"
    if "ordenanza" in c:
        return "ordenanza"
    if "acuerdo" in c:
        return "acuerdo"
    if "conpes" in c:
        return "conpes"
    return "ley"


def _fallback_leyes(text: str) -> list[dict[str, Any]]:
    """Extrae normas de texto markdown libre cuando el modelo no usa pipes."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    # Intenta extraer de secciones "Leyes" / "Marco normativo" / "Documentos"
    sections = _extract_section(
        text,
        "ley", "leyes", "marco normativo", "normativa", "normas", "documentos", "acuerdos", "otros"
    )

    candidates = sections or text.splitlines()

    for raw in candidates:
        line = _clean_line(raw) if raw not in sections else raw
        if not line or len(line) < 5:
            continue
        m = _LEY_RE.search(line)
        if not m:
            continue
        # Toma desde el match hasta el fin de la línea como código
        codigo = line.strip().rstrip(".")
        key = codigo.lower()[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "codigo": codigo,
            "titulo": codigo,
            "tipo": _guess_tipo_ley(codigo),
            "articulos": "",
            "relevancia": "",
            "vigente": "si",
            "jerarquia": "",
        })
    return out


def _fallback_actores(text: str) -> list[dict[str, Any]]:
    """Extrae actores de texto markdown libre."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    sections = _extract_section(
        text,
        "actor", "actores", "entidad", "entidades", "instituciones",
        "responsabilidad", "responsabilidades",
    )
    candidates = sections or text.splitlines()

    for raw in candidates:
        line = _clean_line(raw) if raw not in sections else raw
        if not line or len(line) < 4:
            continue
        # Extrae sigla si existe entre paréntesis
        sigla_m = _SIGLA_RE.search(line)
        sigla = sigla_m.group(1) if sigla_m else ""
        nombre = line.rstrip(".")
        key = nombre.lower()[:40]
        if key in seen:
            continue
        seen.add(key)
        if _NOMBRE_ES_NORMA_RE.match(nombre):
            continue
        out.append({
            "nombre": nombre,
            "sigla": sigla,
            "tipo": "ejecutor",
            "nivel": _guess_nivel(nombre),
            "competencias": "",
        })
    return out


def _fallback_responsabilidades(text: str) -> list[dict[str, Any]]:
    """Extrae responsabilidades de texto markdown libre."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    sections = _extract_section(
        text,
        "responsabilidad", "responsabilidades", "competencia", "obligacion",
    )
    candidates = sections or []

    # Si no hay sección específica, toma todas las líneas de lista
    if not candidates:
        for raw in text.splitlines():
            if re.match(r"^\s*[\d\-\*]", raw):
                cleaned = _clean_line(raw)
                if cleaned and len(cleaned) > 5:
                    candidates.append(cleaned)

    for item in candidates:
        if _TITULO_ES_ACTOR_O_LEY_RE.match(item.strip()):
            continue
        key = item.lower()[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "titulo": item[:120],
            "descripcion": item,
            "tipo": "P",
            "sector": "",
            "referencia_legal": None,
            "obligatoriedad": None,
        })
    return out


def _fallback_brechas(text: str) -> list[dict[str, Any]]:
    """Extrae brechas de texto markdown libre."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    sections = _extract_section(text, "brecha", "brechas", "déficit", "deficit", "problema")
    for item in sections:
        key = item.lower()[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "titulo": item[:80],
            "descripcion": item,
            "tipo": "indefinido",
            "severidad": "media",
            "norma_base": None,
            "recomendacion": None,
        })
    return out


# ---------------------------------------------------------------------------
# Parsers públicos — pipe primero, fallback markdown si 0 resultados
# ---------------------------------------------------------------------------

def parse_responsabilidades(text: str) -> list[dict[str, Any]]:
    out = _parse_pipe_responsabilidades(text)
    return out if out else _fallback_responsabilidades(text)


def parse_leyes(text: str) -> list[dict[str, Any]]:
    out = _parse_pipe_leyes(text)
    return out if out else _fallback_leyes(text)


def parse_actores(text: str) -> list[dict[str, Any]]:
    out = _parse_pipe_actores(text)
    return out if out else _fallback_actores(text)


def parse_brechas(text: str) -> list[dict[str, Any]]:
    out = _parse_pipe_brechas(text)
    return out if out else _fallback_brechas(text)


# ---------------------------------------------------------------------------
# Otros parsers
# ---------------------------------------------------------------------------

def parse_matriz_json(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def parse_coordinator_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return {"accion": "finalizar", "razon": "respuesta no JSON", "confianza": 0.5}
    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"accion": "finalizar", "razon": "JSON inválido del coordinador", "confianza": 0.5}
