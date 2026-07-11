"""Catálogo embebido de categorización municipal (Ley 617/2000).

Generado a partir del Excel oficial de la Contaduría General de la Nación por
`scripts/build_categorizacion_municipios.py` (ver ese archivo para cómo
actualizarlo). Se cruza por nombre normalizado de departamento+municipio con
los resultados en línea del dataset DIVIPOLA (`divipola_search.py`), porque el
"Código CGN" de este catálogo no es compatible con el DIVIPOLA estándar.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.slices.common.territorio import normalize_territorio

_CATALOGO_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "categorizacion_municipios.json"


@lru_cache(maxsize=1)
def _catalogo() -> dict[str, dict]:
    if not _CATALOGO_PATH.is_file():
        return {}
    try:
        return json.loads(_CATALOGO_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def obtener_categoria(departamento: str | None, municipio: str | None) -> dict | None:
    """Busca `{categoria, poblacion_dane, icld_miles}` por nombre de depto/municipio.

    Devuelve None si falta alguno de los dos nombres o no hay match en el catálogo.
    """
    _, depto_clean, muni_clean = normalize_territorio(["COLOMBIA", departamento, municipio])
    if not depto_clean or not muni_clean:
        return None

    key = f"{depto_clean}|{muni_clean}"
    return _catalogo().get(key)
