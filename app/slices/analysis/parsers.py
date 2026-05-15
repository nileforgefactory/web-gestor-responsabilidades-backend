"""Parseo de salidas estructuradas de agentes LLM."""

from __future__ import annotations

import json
import re
from typing import Any


def _split_pipe_line(line: str) -> list[str]:
    return [p.strip() for p in line.split("|")]


def parse_responsabilidades(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-").strip()
        if "|" not in line or len(line) < 8:
            continue
        parts = _split_pipe_line(line)
        if len(parts) < 2:
            continue
        out.append(
            {
                "titulo": parts[0],
                "descripcion": parts[1] if len(parts) > 1 else "",
                "tipo": parts[2] if len(parts) > 2 else "P",
                "sector": parts[3] if len(parts) > 3 else "",
                "referencia_legal": parts[4] if len(parts) > 4 else None,
                "obligatoriedad": parts[5] if len(parts) > 5 else None,
            }
        )
    return out


def parse_leyes(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-").strip()
        if "|" not in line:
            continue
        parts = _split_pipe_line(line)
        if len(parts) < 2:
            continue
        out.append(
            {
                "codigo": parts[0],
                "titulo": parts[1],
                "tipo": parts[2] if len(parts) > 2 else "ley",
                "articulos": parts[3] if len(parts) > 3 else "",
                "relevancia": parts[4] if len(parts) > 4 else "",
                "vigente": parts[5] if len(parts) > 5 else "si",
                "jerarquia": parts[6] if len(parts) > 6 else "",
            }
        )
    return out


def parse_actores(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-").strip()
        if "|" not in line:
            continue
        parts = _split_pipe_line(line)
        if len(parts) < 2:
            continue
        out.append(
            {
                "nombre": parts[0],
                "sigla": parts[1] if len(parts) > 1 else "",
                "tipo": parts[2] if len(parts) > 2 else "principal",
                "nivel": parts[3] if len(parts) > 3 else "municipal",
                "competencias": parts[4] if len(parts) > 4 else "",
            }
        )
    return out


def parse_brechas(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-").strip()
        if "|" not in line:
            continue
        parts = _split_pipe_line(line)
        if len(parts) < 2:
            continue
        out.append(
            {
                "titulo": parts[0],
                "descripcion": parts[1],
                "tipo": parts[2] if len(parts) > 2 else "alerta",
                "severidad": parts[3] if len(parts) > 3 else "media",
                "norma_base": parts[4] if len(parts) > 4 else None,
                "recomendacion": parts[5] if len(parts) > 5 else None,
            }
        )
    return out


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
