"""Descarga de URLs y extracción de texto para validación."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.slices.ocr.extractor import ExtractionResult
from app.slices.rag.extract import extract_document_from_bytes

logger = logging.getLogger(__name__)

_HTML_SUFFIXES = {".html", ".htm", ".asp", ".aspx", ".php"}
_PDF_HINT = ".pdf"
_PDF_MAGIC = b"%PDF"


def _sanitize_pdf_bytes(raw: bytes) -> bytes:
    """
    Recorta basura antes del magic ``%PDF`` (p. ej. ``\\t%PDF`` en portales gov.co).

    Si no hay magic, devuelve el buffer original para que falle con mensaje claro.
    """
    idx = raw.find(_PDF_MAGIC)
    if idx > 0:
        logger.debug("[SCRAPER] pdf_sanitize: recortados %d bytes previos al header", idx)
        return raw[idx:]
    return raw


def _looks_like_pdf(raw: bytes, content_type: str, path_lower: str, filename: str) -> bool:
    ct = content_type.lower()
    if "pdf" in ct:
        return True
    if Path(filename).suffix.lower() == ".pdf":
        return True
    if path_lower.endswith(_PDF_HINT):
        return True
    return raw.lstrip()[:8].startswith(_PDF_MAGIC)


@dataclass(frozen=True)
class FetchedDocument:
    url: str
    text: str
    filename: str
    extraction_method: str
    char_count: int


def _guess_filename(url: str, content_type: str | None) -> str:
    path = urlparse(url).path
    name = Path(path).name
    if name and "." in name:
        return name
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return "documento.pdf"
    if "html" in ct:
        return "documento.html"
    return "documento.txt"


def html_to_text(raw_html: str) -> str:
    """Convierte HTML a texto plano (sin dependencias extra)."""
    text = raw_html
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


async def fetch_and_extract(
    url: str,
    *,
    http: httpx.AsyncClient,
    settings: Settings,
) -> FetchedDocument:
    """
    Descarga una URL y devuelve texto extraído.

    Raises:
        ValueError: descarga vacía, formato no soportado o texto insuficiente.
        httpx.HTTPError: error de red.
    """
    logger.debug("[SCRAPER] fase=descarga url=%s", url)
    headers = {"User-Agent": settings.scraper_user_agent}
    timeout = httpx.Timeout(settings.scraper_fetch_timeout_sec, connect=20.0)

    async with http.stream("GET", url, headers=headers, timeout=timeout, follow_redirects=True) as resp:
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        chunks: list[bytes] = []
        total = 0
        max_bytes = settings.scraper_fetch_max_bytes
        async for block in resp.aiter_bytes():
            total += len(block)
            if total > max_bytes:
                raise ValueError(f"Documento supera el límite de {max_bytes} bytes")
            chunks.append(block)
        raw = b"".join(chunks)

    if not raw:
        raise ValueError("Respuesta vacía")

    filename = _guess_filename(url, content_type)
    suf = Path(filename).suffix.lower()
    path_lower = urlparse(url).path.lower()
    if path_lower.endswith(_PDF_HINT):
        filename = Path(filename).stem + ".pdf" if suf != ".pdf" else filename

    ct = (content_type or "").lower()
    if "html" in ct or suf in _HTML_SUFFIXES or path_lower.endswith(tuple(_HTML_SUFFIXES)):
        text = html_to_text(raw.decode("utf-8", errors="replace"))
        if len(text) < settings.scraper_min_extracted_chars:
            raise ValueError("HTML sin texto normativo suficiente")
        return FetchedDocument(
            url=url,
            text=text,
            filename=filename,
            extraction_method="html",
            char_count=len(text),
        )

    if _looks_like_pdf(raw, ct, path_lower, filename):
        raw = _sanitize_pdf_bytes(raw)
        if not filename.lower().endswith(".pdf"):
            filename = Path(filename).stem + ".pdf"

    try:
        result: ExtractionResult = await extract_document_from_bytes(
            raw, filename, settings=settings
        )
    except ValueError as exc:
        msg = str(exc)
        if "Formato no soportado" in msg and ("text/" in ct or "json" in ct):
            text = raw.decode("utf-8", errors="replace").strip()
            if len(text) >= settings.scraper_min_extracted_chars:
                return FetchedDocument(
                    url=url,
                    text=text,
                    filename="documento.txt",
                    extraction_method="texto_plano",
                    char_count=len(text),
                )
        if _looks_like_pdf(raw, ct, path_lower, filename):
            logger.warning(
                "[SCRAPER] pdf_ilegible url=%s motivo=%s",
                url,
                msg[:200],
            )
            raise ValueError(
                f"PDF ilegible o corrupto ({msg}). Se probará otro enlace."
            ) from exc
        raise

    if result.char_count < settings.scraper_min_extracted_chars:
        raise ValueError("Texto extraído demasiado corto")

    return FetchedDocument(
        url=url,
        text=result.text,
        filename=result.filename,
        extraction_method=result.extraction_method.value,
        char_count=result.char_count,
    )
