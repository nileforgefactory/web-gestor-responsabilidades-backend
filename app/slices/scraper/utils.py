"""Utilidades del scraper (slugs, tipo normativo, dominios, consultas)."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse


def build_search_query(norma: str, *, suffix: str) -> str:
    """
    Arma la consulta principal añadiendo palabras del sufijo que aún no estén en la norma.

    Evita duplicar \"Colombia\" y siempre separa con espacio (nunca ``1991Colombia``).
    """
    base = norma.strip()
    if not base:
        return base
    extra_words: list[str] = []
    for word in suffix.split():
        w = word.strip()
        if not w:
            continue
        if w.lower() not in base.lower():
            extra_words.append(w)
    if not extra_words:
        return base
    return f"{base} {' '.join(extra_words)}"


def build_search_query_variants(norma: str, *, suffix: str, max_variants: int = 3) -> list[str]:
    """Variantes de búsqueda para mejorar recall (Constitución, leyes conocidas, etc.)."""
    base = norma.strip()
    if not base:
        return []

    primary = build_search_query(base, suffix=suffix)
    candidates: list[str] = [
        primary,
        base,
        f"{base} PDF",
        f"{base} texto oficial",
        f"{_strip_accents(base)} PDF",
    ]
    if "constitucion" in base.lower() or "constitución" in base.lower():
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
