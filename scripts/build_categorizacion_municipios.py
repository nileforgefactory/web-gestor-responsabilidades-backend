"""Genera app/data/categorizacion_municipios.json a partir del Excel oficial de
categorización municipal (Ley 617/2000) publicado anualmente por la Contaduría
General de la Nación (CGN).

No requiere dependencias externas (solo stdlib: zipfile + xml.etree.ElementTree)
para no agregar openpyxl/pandas al backend en runtime.

Cómo actualizar el catálogo (usualmente 1 vez al año, cuando sale la nueva
resolución de categorización):

1. Descargar el Excel vigente desde:
   https://www.contaduria.gov.co/categorizacion-de-departamentos-distritos-y-municipios
   (buscar el enlace "CT01 Categorizacion.xlsx" de la resolución más reciente).
2. Ejecutar:
       python scripts/build_categorizacion_municipios.py <ruta_al_xlsx_descargado>
3. Confirmar el resumen impreso (cantidad de municipios, ejemplos) y hacer commit
   del `app/data/categorizacion_municipios.json` actualizado.

El cruce con los resultados en línea de datos.gov.co (dataset DIVIPOLA, ver
`app/slices/common/divipola_search.py`) se hace por nombre normalizado de
departamento+municipio (mismo criterio que `app/slices/common/territorio.py`),
no por código, porque el "Código CGN" de este Excel (9 dígitos) no es
compatible con el DIVIPOLA estándar de 5 dígitos.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

_ADMIN_PREFIX = {
    "DEPARTAMENTO", "DEPARTAMENT", "DEPTO", "DEPT", "DEP",
    "MUNICIPIO", "MUNICIPI", "MUNICIPAL", "MUNICIPALITY",
    "CIUDAD", "DISTRITO", "DIST",
}
_ARTICLES = {"DE", "DEL", "LA", "EL", "LOS", "LAS"}

_OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "categorizacion_municipios.json"
_SHEET_MUNICIPIOS = "xl/worksheets/sheet3.xml"  # "Categorización por Municipios"


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _clean_name(raw: str) -> str:
    """Normaliza igual que app/slices/common/territorio.py (mayúsculas, sin
    tildes, sin prefijos administrativos) para que la clave calce con los
    nombres que devuelve el dataset DIVIPOLA de datos.gov.co."""
    text = _strip_accents(raw.strip().upper())
    tokens = [t for t in re.split(r"[\s\-_/]+", text) if t]
    while tokens and tokens[0] in _ADMIN_PREFIX:
        tokens.pop(0)
    while tokens and tokens[0] in _ARTICLES:
        tokens.pop(0)
    return " ".join(tokens)


def _load_shared_strings(z: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.findall(".//m:t", _NS)) for si in root.findall("m:si", _NS)]


def _cell_value(cell: ET.Element, shared: list[str]):
    v = cell.find("m:v", _NS)
    if v is None or v.text is None:
        return None
    if cell.get("t") == "s":
        return shared[int(v.text)]
    try:
        return float(v.text) if ("." in v.text or "e" in v.text.lower()) else int(v.text)
    except ValueError:
        return v.text


def _col_letters(ref: str) -> str:
    match = re.match(r"[A-Z]+", ref)
    if not match:
        raise ValueError(f"Referencia de celda inválida: {ref!r}")
    return match.group(0)


def build(xlsx_path: Path) -> dict[str, dict]:
    with zipfile.ZipFile(xlsx_path) as z:
        shared = _load_shared_strings(z)
        root = ET.fromstring(z.read(_SHEET_MUNICIPIOS))
        rows = root.findall(".//m:sheetData/m:row", _NS)

        header_map: dict[str, str] = {}
        data_rows: list[dict[str, object]] = []
        for row in rows:
            cells = {_col_letters(c.get("r")): _cell_value(c, shared) for c in row.findall("m:c", _NS)}
            if not any(v is not None for v in cells.values()):
                continue
            texts = [v for v in cells.values() if isinstance(v, str)]
            if not header_map and "Nombre departamento" in texts:
                header_map = {letter: val for letter, val in cells.items() if isinstance(val, str)}
                continue
            if header_map:
                data_rows.append(cells)

        if not header_map:
            raise RuntimeError(
                "No se encontró la fila de encabezado 'Nombre departamento' en "
                f"{_SHEET_MUNICIPIOS}. El formato del Excel de la Contaduría pudo haber cambiado."
            )

        def find_col(*names: str) -> str | None:
            for letter, val in header_map.items():
                if any(n.lower() in val.lower() for n in names):
                    return letter
            return None

        col_depto = find_col("Nombre departamento")
        col_muni = find_col("Nombre municipio")
        col_pob = find_col("Poblacion", "Población")
        col_icld = find_col("ICLD")
        col_cat = find_col("Categoria", "Categoría")
        if not (col_depto and col_muni and col_cat):
            raise RuntimeError(f"Columnas esperadas no encontradas en encabezado: {header_map!r}")

        result: dict[str, dict] = {}
        for cells in data_rows:
            depto, muni, categoria = cells.get(col_depto), cells.get(col_muni), cells.get(col_cat)
            if not isinstance(depto, str) or not isinstance(muni, str):
                continue
            key = f"{_clean_name(depto)}|{_clean_name(muni)}"
            result[key] = {
                "categoria": str(categoria) if categoria is not None else None,
                "poblacion_dane": cells.get(col_pob),
                "icld_miles": cells.get(col_icld),
            }
        return result


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Uso: python {sys.argv[0]} <ruta_al_xlsx_de_categorizacion>", file=sys.stderr)
        sys.exit(1)

    xlsx_path = Path(sys.argv[1])
    if not xlsx_path.is_file():
        print(f"Archivo no encontrado: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    result = build(xlsx_path)
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(f"OK: {len(result)} municipios escritos en {_OUT_PATH}")
    for key in list(result)[:5]:
        print(f"  {key}: {result[key]}")


if __name__ == "__main__":
    main()
