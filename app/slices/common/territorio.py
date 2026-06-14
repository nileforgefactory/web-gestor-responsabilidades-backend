"""Convención territorial [País, Departamento, Municipio] para normativa colombiana."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

TERRITORIO_LEN = 3
DEFAULT_PAIS = "COLOMBIA"

_COUNTRY_ABBREVIATIONS = frozenset({"C", "CO", "COL", "COLO", "COL."})

_ADMIN_PREFIX_TOKENS = frozenset(
    {
        "DEPARTAMENTO",
        "DEPARTAMENT",
        "DEPTO",
        "DEPT",
        "DEP",
        "MUNICIPIO",
        "MUNICIPI",
        "MUNICIPAL",
        "MUNICIPALITY",
        "CIUDAD",
        "DISTRITO",
        "DIST",
    }
)

_LEADING_ARTICLE_TOKENS = frozenset({"DE", "DEL", "LA", "EL", "LOS", "LAS"})

_COUNTRY_PREFIX_TOKENS = frozenset({"REPUBLICA", "REPÚBLICA", "RE"})


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _tokenize(name: str) -> list[str]:
    return [token for token in re.split(r"[\s\-_/]+", name) if token]


def _is_country_abbreviation(value: str) -> bool:
    compact = value.replace(".", "").upper()
    return compact in _COUNTRY_ABBREVIATIONS or len(compact) <= 3


def _normalize_country_name(raw: str) -> str:
    text = _strip_accents(raw.strip().upper())
    tokens = _tokenize(text)
    if not tokens:
        return DEFAULT_PAIS

    compact = "".join(tokens).replace(".", "")
    if _is_country_abbreviation(compact):
        return DEFAULT_PAIS

    while tokens and tokens[0] in _COUNTRY_PREFIX_TOKENS:
        tokens.pop(0)
    while tokens and tokens[0] in _LEADING_ARTICLE_TOKENS:
        tokens.pop(0)

    if not tokens or _is_country_abbreviation("".join(tokens)):
        return DEFAULT_PAIS
    if tokens == ["COLOMBIA"]:
        return DEFAULT_PAIS
    return " ".join(tokens)


def _normalize_place_name(raw: str) -> str:
    """Nombre limpio de departamento o municipio (sin prefijos administrativos)."""
    text = _strip_accents(raw.strip().upper())
    tokens = _tokenize(text)
    if not tokens:
        return ""

    while tokens and tokens[0] in _ADMIN_PREFIX_TOKENS:
        tokens.pop(0)
    while tokens and tokens[0] in _LEADING_ARTICLE_TOKENS:
        tokens.pop(0)

    return " ".join(tokens)


def _clean_territorial_segment(raw: str | None, *, level: int) -> str | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None

    if level == 0:
        return _normalize_country_name(str(raw))

    cleaned = _normalize_place_name(str(raw))
    if not cleaned:
        return None

    # Rechaza siglas cortas en departamento/municipio (ej. HU, NE).
    if len(cleaned.replace(" ", "")) <= 2:
        return None

    return cleaned


def normalize_territorio(raw: Any) -> list[str | None]:
    """
    Normaliza a ``[pais, departamento, municipio]``.

    - Todo en MAYÚSCULAS, sin tildes.
    - País: nombre completo (``COLOMBIA``); expande siglas ``CO``, ``COL``, etc.
    - Departamento/municipio: sin prefijos ``Departamento de`` / ``Municipio de``.
    - Nacional: ``[COLOMBIA, None, None]``.
    - Departamental: ``[COLOMBIA, CAUCA, None]``.
    - Municipal: ``[COLOMBIA, CAUCA, CAJIBIO]``.
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

    pais = _clean_territorial_segment(items[0], level=0) or DEFAULT_PAIS
    departamento = _clean_territorial_segment(items[1], level=1)
    municipio = _clean_territorial_segment(items[2], level=2)

    if municipio and not departamento:
        departamento = None

    return [pais, departamento, municipio]


def territorio_normalization_warnings(raw: Any) -> list[str]:
    """Advertencias cuando el modelo devolvió siglas o prefijos administrativos."""
    if raw is None:
        return []

    if isinstance(raw, dict):
        items = [
            raw.get("pais") or raw.get("país") or raw.get("country"),
            raw.get("departamento") or raw.get("department") or raw.get("depto"),
            raw.get("municipio") or raw.get("municipality") or raw.get("ciudad"),
        ]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return []

    warnings: list[str] = []
    labels = ("país", "departamento", "municipio")

    for idx, (label, value) in enumerate(zip(labels, items, strict=False)):
        if value is None or not str(value).strip():
            continue
        text = str(value).strip().upper()
        if idx == 0 and _is_country_abbreviation(text.replace(".", "")):
            warnings.append(
                f"Territorio: sigla de país corregida ({text!r} → {DEFAULT_PAIS})."
            )
        if idx > 0:
            tokens = _tokenize(_strip_accents(text))
            if tokens and tokens[0] in _ADMIN_PREFIX_TOKENS:
                warnings.append(
                    f"Territorio: prefijo administrativo eliminado en {label} ({text!r})."
                )
            if len(text.replace(" ", "")) <= 2:
                warnings.append(
                    f"Territorio: posible sigla en {label} ({text!r}); use nombre completo."
                )

    return warnings


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


def collection_id_from_territorio(territorio: list[str | None] | Any) -> str:
    """
    ID de colección lógica: ``PAIS[_DEPARTAMENTO[_MUNICIPIO]]`` en MAYÚSCULAS.

    - Nacional: ``COLOMBIA``
    - Departamental: ``COLOMBIA_CAUCA``
    - Municipal: ``COLOMBIA_CAUCA_CAJIBIO``
    """
    pais, departamento, municipio = normalize_territorio(territorio)
    parts = [_segment_for_collection_id(pais)]
    if departamento:
        parts.append(_segment_for_collection_id(departamento))
    if municipio:
        parts.append(_segment_for_collection_id(municipio))
    return "_".join(parts)


def _segment_for_collection_id(clean_name: str) -> str:
    """Token de colección: MAYÚSCULAS, sin tildes, palabras unidas con ``_``."""
    return "_".join(_tokenize(clean_name))


def resolve_scraper_pais(value: str | None, *, default: str = DEFAULT_PAIS) -> str:
    """País efectivo del scraper (MAYÚSCULAS, nombre completo)."""
    if value is not None and str(value).strip():
        return normalize_territorio([value, None, None])[0]
    return normalize_territorio([default, None, None])[0]


def pais_label_for_search(pais: str) -> str:
    """Etiqueta legible para consultas web (``COLOMBIA`` → ``Colombia``)."""
    return " ".join(part.capitalize() for part in pais.split())


def allowed_collection_ids(territorio: list[str | None] | Any) -> frozenset[str]:
    """
    Colecciones visibles para un usuario según su territorio.

    Incluye la colección propia y las ancestros (nivel departamental con municipio
    ``None``, y nacional). No incluye municipios hermanos (ej. Neiva vs Palermo).

    Ej. ``[COLOMBIA, HUILA, PALERMO]`` →
    ``{COLOMBIA, COLOMBIA_HUILA, COLOMBIA_HUILA_PALERMO}``.
    """
    pais, departamento, municipio = normalize_territorio(territorio)
    ids: set[str] = {collection_id_from_territorio([pais, None, None])}
    if departamento:
        ids.add(collection_id_from_territorio([pais, departamento, None]))
    if municipio and departamento:
        ids.add(collection_id_from_territorio([pais, departamento, municipio]))
    return frozenset(ids)


def is_collection_allowed(territorio: list[str | None] | Any, collection_id: str) -> bool:
    """True si ``collection_id`` está dentro del ámbito territorial del usuario."""
    return collection_id.strip().upper() in allowed_collection_ids(territorio)


def apply_pais_scope(
    territorio: list[str | None],
    pais: str,
) -> tuple[list[str | None], list[str]]:
    """Fija el país del territorio al ámbito solicitado en la búsqueda."""
    scoped = normalize_territorio(territorio)
    pais_norm = resolve_scraper_pais(pais)
    warnings: list[str] = []
    if scoped[0] != pais_norm:
        warnings.append(
            f"País ajustado al ámbito de búsqueda ({scoped[0]!r} → {pais_norm!r})."
        )
        scoped[0] = pais_norm
    return scoped, warnings
