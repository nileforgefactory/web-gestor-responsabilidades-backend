"""Convención territorial [País, Departamento, Municipio] para normativa colombiana."""

from __future__ import annotations

import json
from typing import Any

TERRITORIO_LEN = 3
DEFAULT_PAIS = "COLOMBIA"


def normalize_territorio(raw: Any) -> list[str | None]:
    """
    Normaliza a ``[pais, departamento, municipio]``.

    - País por defecto: COLOMBIA (mayúsculas).
    - Nivel nacional: ``[COLOMBIA, None, None]``.
    - Departamental: ``[COLOMBIA, HUILA, None]``.
    - Municipal: ``[COLOMBIA, HUILA, NEIVA]``.
    """
    items: list[Any]

    if raw is None:
        return [DEFAULT_PAIS, None, None]

    if isinstance(raw, dict):
        items = [
            raw.get("pais") or raw.get("país") or raw.get("country"),
            raw.get("departamento") or raw.get("department") or raw.get("depto"),
            raw.get("municipio") or raw.get("municipality") or raw.get("ciudad"),
        ]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                return normalize_territorio(parsed)
            except json.JSONDecodeError:
                pass
        parts = [p.strip() for p in text.split(",") if p.strip()]
        items = parts
    else:
        return [DEFAULT_PAIS, None, None]

    while len(items) < TERRITORIO_LEN:
        items.append(None)
    items = items[:TERRITORIO_LEN]

    out: list[str | None] = []
    for i, val in enumerate(items):
        if val is None or (isinstance(val, str) and not val.strip()):
            out.append(None)
            continue
        text = str(val).strip().upper()
        if i == 0 and not text:
            text = DEFAULT_PAIS
        out.append(text or None)

    if out[0] is None:
        out[0] = DEFAULT_PAIS
    return out


def territorio_to_json(territorio: list[str | None]) -> str:
    """Serializa para MySQL (JSON en TEXT)."""
    normalized = normalize_territorio(territorio)
    return json.dumps(normalized, ensure_ascii=False)


def territorio_from_json(raw: str | None) -> list[str | None] | None:
    if not raw:
        return None
    try:
        return normalize_territorio(json.loads(raw))
    except json.JSONDecodeError:
        return None


def _segment_for_collection_id(value: str) -> str:
    """Convierte un segmento territorial a forma legible (ej. HUILA → Huila)."""
    words = value.strip().split()
    return "_".join(w[:1].upper() + w[1:].lower() if w else "" for w in words)


def collection_id_from_territorio(territorio: list[str | None] | Any) -> str:
    """
    ID de colección lógica según ámbito territorial.

    - Nacional: ``Colombia``
    - Departamental: ``Colombia_Huila``
    - Municipal: ``Colombia_Huila_Neiva``
    """
    pais, departamento, municipio = normalize_territorio(territorio)
    parts = [_segment_for_collection_id(pais)]
    if departamento:
        parts.append(_segment_for_collection_id(departamento))
    if municipio:
        parts.append(_segment_for_collection_id(municipio))
    return "_".join(parts)
