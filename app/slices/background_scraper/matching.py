"""Normalización y extracción de clave para detectar normas ya indexadas.

El nombre guardado en `base_conocimiento.nombre` cuando el usuario sube un
archivo manualmente es el nombre de archivo tal cual (ej.
``"constitucion-politica-de-colombia-91 (1).pdf"``), que nunca coincide
textualmente con el nombre canónico del catálogo (ej.
``"Constitución Política de Colombia 1991"``). Comparar por igualdad de
string ingenua falla siempre que difieren tildes, guiones, extensión o
sufijos de colisión de nombre.

Este módulo normaliza el texto (sin tildes, minúsculas, separadores
colapsados) y, cuando es posible, extrae una clave estructurada
``tipo+numero+año`` (ej. ``"ley152 1994"``) a partir de nombre de archivo o
título, que es la forma más confiable de identificar la misma norma sin
importar cómo esté escrito el nombre.
"""

from __future__ import annotations

import re
import unicodedata

_TIPO_NUMERO_ANIO_RE = re.compile(
    r"\b(ley|decreto|conpes|resolucion|circular)\w*\D{0,10}(\d+)\D+(\d{4})\b"
)


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin tildes, separadores no alfanuméricos colapsados a espacio."""
    if not texto:
        return ""
    sin_tildes = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    sin_tildes = sin_tildes.lower()
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes).strip()


def clave_norma(nombre: str) -> str | None:
    """
    Extrae una clave estable ``tipo+numero año`` para identificar la norma
    sin importar el formato del nombre de archivo/título.

    - ``"Ley 152 de 1994"`` / ``"ley-152-de-1994.pdf"`` → ``"ley152 1994"``
    - ``"Constitución Política de Colombia 1991"`` /
      ``"constitucion-politica-de-colombia-91 (1).pdf"`` → ``"constitucion"``
    - Si no se reconoce ningún patrón, retorna ``None``.
    """
    norm = normalizar_texto(nombre)
    if not norm:
        return None
    if "constitucion" in norm:
        return "constitucion"
    match = _TIPO_NUMERO_ANIO_RE.search(norm)
    if match:
        tipo, numero, anio = match.groups()
        return f"{tipo[:6]}{numero} {anio}"
    return None


def claves_posibles(nombre: str) -> set[str]:
    """
    Todas las claves útiles para comparar un nombre contra el catálogo:
    la clave estructurada (si se reconoce) y el texto normalizado completo
    como respaldo para coincidencias exactas tras normalizar.
    """
    claves: set[str] = set()
    estructurada = clave_norma(nombre)
    if estructurada:
        claves.add(estructurada)
    normalizado = normalizar_texto(nombre)
    if normalizado:
        claves.add(normalizado)
    return claves
