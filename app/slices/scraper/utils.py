"""Utilidades del scraper (slugs, tipo normativo, dominios, consultas)."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from app.slices.common.territorio import pais_label_for_search


def build_search_query(norma: str, *, suffix: str, pais: str | None = None) -> str:
    """
    Arma la consulta principal añadiendo país (si aplica) y palabras del sufijo.

    Evita duplicar el país y siempre separa con espacio (nunca ``1991Colombia``).
    """
    base = norma.strip()
    if not base:
        return base

    prefix_words: list[str] = []
    if pais:
        label = pais_label_for_search(pais)
        if label.lower() not in base.lower():
            prefix_words.append(label)

    extra_words: list[str] = []
    for word in suffix.split():
        w = word.strip()
        if not w:
            continue
        if w.lower() in base.lower():
            continue
        if any(w.lower() == p.lower() for p in prefix_words):
            continue
        extra_words.append(w)

    parts = [*prefix_words, base, *extra_words]
    return " ".join(parts)


def build_search_query_variants(
    norma: str,
    *,
    suffix: str,
    max_variants: int = 3,
    pais: str | None = None,
) -> list[str]:
    """Variantes de búsqueda para mejorar recall (Constitución, leyes conocidas, etc.)."""
    base = norma.strip()
    if not base:
        return []

    pais_label = pais_label_for_search(pais) if pais else None
    primary = build_search_query(base, suffix=suffix, pais=pais)
    candidates: list[str] = [
        primary,
        build_search_query(base, suffix="PDF", pais=pais),
        build_search_query(base, suffix="texto oficial", pais=pais),
        f"{base} PDF",
        f"{_strip_accents(base)} PDF",
    ]
    if pais_label and pais_label.lower() not in base.lower():
        candidates.insert(1, f"{pais_label} {base} PDF")

    if "constitucion" in base.lower() or "constitución" in base.lower():
        if pais_label:
            candidates.insert(1, f"Constitución Política de {pais_label} 1991 PDF")
        else:
            candidates.insert(1, "Constitución Política de Colombia 1991 PDF")

    seen: set[str] = set()
    out: list[str] = []
    for q in candidates:
        key = q.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q.strip())
        if len(out) >= max(1, max_variants):
            break
    return out


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def derive_document_id(norma: str) -> str:
    """Identificador estable para Qdrant a partir del nombre de la norma."""
    slug = re.sub(r"[^\w\-]+", "-", norma.strip().lower(), flags=re.UNICODE).strip("-")
    return (slug[:120] or "norma")


def infer_tipo_norma(norma: str) -> str:
    """Tipo para catálogo base_conocimiento."""
    n = norma.lower()
    if "constitucion" in n or "constitución" in n:
        return "ley"
    if "decreto" in n:
        return "decreto"
    if "resolución" in n or "resolucion" in n:
        return "resolucion"
    if "circular" in n:
        return "circular"
    if "ley" in n or "código" in n or "codigo" in n:
        return "ley"
    return "otro"


def allowed_domains_list(raw: str) -> list[str]:
    """Lista de dominios permitidos desde configuración."""
    if not raw.strip():
        return []
    return [d.strip().lower().lstrip(".") for d in raw.split(",") if d.strip()]


def url_domain_allowed(url: str, allowed: list[str]) -> bool:
    """True si no hay restricción o el host coincide con algún dominio permitido."""
    if not allowed:
        return True
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    if host.startswith("www."):
        host = host[4:]
    for domain in allowed:
        if host == domain or host.endswith("." + domain):
            return True
    return False
