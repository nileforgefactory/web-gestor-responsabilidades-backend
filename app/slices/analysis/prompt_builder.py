from pathlib import Path

_TEMPLATES = Path(__file__).resolve().parents[3] / "data" / "prompts"

_JERARQUIA = """
## Jerarquía jurídica colombiana (resumen)
Constitución > Ley > Decreto > Resolución > Ordenanza > Acuerdo.
Una norma inferior no puede contradecir una superior.
"""

_NIVEL_CTX = {
    "municipal": "Prioriza Ley 136/1994, Ley 715/2001, Ley 152/1994 (planes de desarrollo municipal).",
    "departamental": "Prioriza LOOT, SGP departamental, coordinación con municipios.",
    "nacional": "Prioriza Constitución arts. organización del Estado y política nacional.",
    "sectorial": "Enfoque sectorial transversal del plan analizado.",
}

_PROFUNDIDAD = {
    "basico": "Extrae máximo 10 responsabilidades y 5 leyes principales.",
    "estandar": "Extrae todas las responsabilidades, leyes y actores citados.",
    "profundo": "Análisis exhaustivo incluyendo brechas y omisiones normativas.",
}


def build_agent_prompt(
    agent_type: str,
    *,
    nivel: str,
    profundidad: str,
    entidad: str = "",
) -> str:
    """
    Ensambla system prompt: jerarquía jurídica + nivel + profundidad + template MD.

    Args:
        agent_type: Nombre del archivo en ``data/prompts/{agent_type}.md``.
    """
    parts = [_JERARQUIA, _NIVEL_CTX.get(nivel, ""), _PROFUNDIDAD.get(profundidad, _PROFUNDIDAD["estandar"])]
    tpl = _TEMPLATES / f"{agent_type}.md"
    if tpl.exists():
        parts.append(tpl.read_text(encoding="utf-8"))
    if entidad:
        parts.append(f"## Entidad\n{entidad}\n")
    return "\n\n".join(p for p in parts if p.strip())
