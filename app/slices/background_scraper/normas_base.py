"""
Catálogo de normas que el sistema necesita indexar para funcionar correctamente.

Son los documentos de referencia obligatoria para analizar planes de desarrollo
territoriales en Colombia: constitución, leyes orgánicas, decretos reglamentarios,
políticas sectoriales y marcos de competencias.
"""

from __future__ import annotations

# Cada entrada: (codigo, prioridad)
# prioridad 1=crítica, 2=importante, 3=complementaria
NORMAS_BASE: list[tuple[str, int]] = [
    # ── Constitución y marcos orgánicos ────────────────────────────────────
    ("Constitución Política de Colombia 1991", 1),
    ("Ley 152 de 1994",  1),   # Ley Orgánica del Plan de Desarrollo
    ("Ley 136 de 1994",  1),   # Régimen Municipal
    ("Ley 715 de 2001",  1),   # Sistema General de Participaciones
    ("Ley 1551 de 2012", 1),   # Organización y funcionamiento de municipios
    ("Ley 617 de 2000",  1),   # Ajuste fiscal territorial y categorías
    ("Ley 388 de 1997",  1),   # Desarrollo territorial y POT

    # ── Presupuesto y finanzas públicas ────────────────────────────────────
    ("Decreto 111 de 1996",   1),  # Estatuto Orgánico del Presupuesto
    ("Ley 819 de 2003",       2),  # Marco fiscal de mediano plazo
    ("Ley 1530 de 2012",      2),  # Sistema General de Regalías
    ("Ley 358 de 1997",       2),  # Endeudamiento territorial

    # ── Contratación pública ───────────────────────────────────────────────
    ("Ley 80 de 1993",        1),  # Estatuto General de Contratación
    ("Ley 1150 de 2007",      1),  # Reforma a contratación pública
    ("Decreto 1082 de 2015",  2),  # Decreto único sector planeación

    # ── Organización del Estado ────────────────────────────────────────────
    ("Ley 489 de 1998",       2),  # Organización y funcionamiento entidades Estado
    ("Ley 909 de 2004",       2),  # Empleo público y carrera administrativa
    ("Ley 734 de 2002",       2),  # Código Disciplinario Único

    # ── Transparencia y anticorrupción ─────────────────────────────────────
    ("Ley 1474 de 2011",      1),  # Estatuto Anticorrupción
    ("Ley 1712 de 2014",      2),  # Transparencia y acceso a información pública
    ("Ley 190 de 1995",       2),  # Estatuto Anticorrupción original

    # ── Sectores sociales ──────────────────────────────────────────────────
    ("Ley 115 de 1994",       2),  # Ley General de Educación
    ("Ley 100 de 1993",       2),  # Sistema de Seguridad Social Integral
    ("Ley 1098 de 2006",      2),  # Código de Infancia y Adolescencia
    ("Ley 1257 de 2008",      2),  # No violencia contra la mujer
    ("Ley 1145 de 2007",      3),  # Sistema Nacional de Discapacidad

    # ── Medio ambiente ─────────────────────────────────────────────────────
    ("Ley 99 de 1993",        1),  # Sistema Nacional Ambiental - SINA
    ("Ley 373 de 1997",       3),  # Uso eficiente del agua
    ("Ley 1523 de 2012",      2),  # Gestión del riesgo de desastres

    # ── Planes nacionales de desarrollo ────────────────────────────────────
    ("Ley 2294 de 2023",      1),  # PND Colombia Potencia Mundial de la Vida 2022-2026
    ("Ley 1955 de 2019",      2),  # PND Pacto por Colombia 2018-2022
    ("Ley 1753 de 2015",      3),  # PND Todos por un Nuevo País 2014-2018

    # ── Políticas y CONPES ─────────────────────────────────────────────────
    ("CONPES 3918 de 2018",   2),  # Estrategia ODS
    ("CONPES 3951 de 2018",   3),  # Ciudades sostenibles
    ("CONPES 4050 de 2021",   3),  # Política de Datos Abiertos

    # ── Competencias específicas ───────────────────────────────────────────
    ("Ley 1454 de 2011",      2),  # Ley Orgánica de Ordenamiento Territorial - LOOT
    ("Ley 1625 de 2013",      2),  # Régimen de Áreas Metropolitanas
    ("Ley 128 de 1994",       3),  # Ley de Áreas Metropolitanas (derogada parcialmente)
    ("Ley 1776 de 2016",      3),  # Zonas más afectadas por el conflicto - ZOMAC
]


def get_normas_by_priority(max_priority: int = 3) -> list[str]:
    """Retorna códigos de normas hasta la prioridad indicada (1=solo críticas, 3=todas)."""
    return [cod for cod, pri in NORMAS_BASE if pri <= max_priority]
