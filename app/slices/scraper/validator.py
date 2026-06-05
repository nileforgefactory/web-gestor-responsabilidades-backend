"""Validación con LLM de que el documento descargado es la norma solicitada."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ollama_client import ollama_chat
from app.slices.rag.service import _with_retries
from app.slices.common.territorio import (
    normalize_territorio,
    resolve_scraper_pais,
    territorio_normalization_warnings,
)
from app.slices.scraper.schemas import ValidacionNormaOut

logger = logging.getLogger(__name__)

_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "prompts" / "scraper_validacion.md"
)


@dataclass(frozen=True)
class ValidationResult:
    outcome: ValidacionNormaOut
    accepted: bool


def _load_system_prompt() -> str:
    if _PROMPT_PATH.is_file():
        return _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return (
        "Decide si el texto corresponde a la norma solicitada. "
        "Responde solo JSON con es_documento_esperado, confianza, codigo_detectado, motivo, "
        "advertencias, territorio ([pais, departamento, municipio])."
    )


def _parse_validation_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return {
            "es_documento_esperado": False,
            "confianza": 0.0,
            "motivo": "El modelo no devolvió JSON válido.",
            "advertencias": [],
            "territorio": ["COLOMBIA", None, None],
        }
    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {
        "es_documento_esperado": False,
        "confianza": 0.0,
        "motivo": "JSON de validación inválido.",
        "advertencias": [],
        "territorio": ["COLOMBIA", None, None],
    }


def _to_outcome(data: dict[str, Any]) -> ValidacionNormaOut:
    conf_raw = data.get("confianza", 0.0)
    try:
        confianza = float(conf_raw)
    except (TypeError, ValueError):
        confianza = 0.0
    confianza = max(0.0, min(1.0, confianza))
    esperado = bool(data.get("es_documento_esperado", False))
    codigo = data.get("codigo_detectado")
    motivo = data.get("motivo")
    advertencias = data.get("advertencias") or []
    if not isinstance(advertencias, list):
        advertencias = []
    territorio_raw = data.get("territorio") or data.get("ambito_territorial")
    territorio = normalize_territorio(territorio_raw)
    extra_warnings = territorio_normalization_warnings(territorio_raw)
    if extra_warnings:
        advertencias = [*advertencias, *extra_warnings]
    return ValidacionNormaOut(
        es_documento_esperado=esperado,
        confianza=confianza,
        codigo_detectado=str(codigo) if codigo else None,
        motivo=str(motivo) if motivo else None,
        advertencias=[str(a) for a in advertencias[:10]],
        territorio=territorio,
    )


async def validate_norm_document(
    *,
    http: httpx.AsyncClient,
    settings: Settings,
    norma_solicitada: str,
    texto: str,
    url: str,
    titulo_resultado: str | None = None,
    pais_esperado: str = "COLOMBIA",
) -> ValidationResult:
    """Pide al LLM confirmar si el texto corresponde a la norma pedida."""
    pais_objetivo = resolve_scraper_pais(pais_esperado)
    if not settings.use_ollama:
        logger.warning("[SCRAPER] norma=%r validacion omitida (use_ollama=false)", norma_solicitada)
        outcome = ValidacionNormaOut(
            es_documento_esperado=True,
            confianza=0.5,
            motivo="Validación IA deshabilitada; se acepta por configuración.",
            advertencias=["use_ollama=false"],
            territorio=normalize_territorio([pais_objetivo, None, None]),
        )
        return ValidationResult(
            outcome=outcome,
            accepted=outcome.confianza >= settings.scraper_validation_min_confidence,
        )

    max_chars = settings.scraper_validation_text_max_chars
    muestra = texto[:max_chars]
    user = f"""País objetivo de búsqueda: {pais_objetivo}
Norma solicitada: {norma_solicitada}
URL del PDF: {url}
Título en resultados de búsqueda: {titulo_resultado or "(sin título)"}

El archivo es un PDF. Debe ser el texto oficial de la norma solicitada, NO un documento que solo la mencione o analice.

Texto extraído del PDF (extracto):
{muestra}
""".strip()

    logger.info(
        "[SCRAPER] norma=%r fase=validacion_ia modelo=%s",
        norma_solicitada,
        settings.ollama_chat_model,
    )

    async def call() -> str:
        return await ollama_chat(
            http=http,
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            messages=[
                {"role": "system", "content": _load_system_prompt()},
                {"role": "user", "content": user},
            ],
        )

    raw = await _with_retries(call, attempts=3)
    data = _parse_validation_json(raw)
    outcome = _to_outcome(data)
    accepted = (
        outcome.es_documento_esperado
        and outcome.confianza >= settings.scraper_validation_min_confidence
    )
    logger.info(
        "[SCRAPER] norma=%r fase=validacion_ia aceptada=%s confianza=%.2f esperado=%s territorio=%s",
        norma_solicitada,
        accepted,
        outcome.confianza,
        outcome.es_documento_esperado,
        outcome.territorio,
    )
    return ValidationResult(outcome=outcome, accepted=accepted)
