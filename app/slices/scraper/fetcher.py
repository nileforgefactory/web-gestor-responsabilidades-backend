"""Descarga de URLs PDF y extracción de texto para validación."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.slices.ocr.extractor import ExtractionResult
from app.slices.rag.extract import extract_document_from_bytes
from app.slices.common.network_errors import NetworkErrorKind, classify_http_error
from app.slices.scraper.utils import url_looks_like_pdf

logger = logging.getLogger(__name__)

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
    if "pdf" in (content_type or "").lower():
        return "documento.pdf"
    return "documento.pdf"


async def fetch_and_extract(
    url: str,
    *,
    http: httpx.AsyncClient,
    settings: Settings,
) -> FetchedDocument:
    """
    Descarga una URL PDF y devuelve texto extraído.

    Solo acepta archivos PDF (URL con indicio de PDF y contenido ``%PDF`` o
    ``application/pdf``). Rechaza HTML, texto plano y otros formatos.

    Raises:
        ValueError: enlace no PDF, descarga vacía, PDF ilegible o texto insuficiente.
        httpx.HTTPError: error de red tras agotar reintentos.
    """
    attempts = max(1, settings.scraper_fetch_retries)
    verify = settings.scraper_fetch_verify_ssl
    last_exc: BaseException | None = None

    for attempt in range(attempts):
        try:
            return await _fetch_and_extract_once(
                url,
                http=http,
                settings=settings,
                verify=verify,
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            info = classify_http_error(exc)
            is_last = attempt >= attempts - 1

            if (
                info.kind == NetworkErrorKind.SSL
                and settings.scraper_fetch_ssl_fallback
                and verify
            ):
                logger.warning(
                    "[SCRAPER] descarga_ssl url=%s reintento_sin_verificar=true",
                    url,
                )
                verify = False
                continue

            if info.retryable and not is_last:
                logger.warning(
                    "[SCRAPER] descarga_reintento url=%s intento=%d/%d tipo=%s",
                    url,
                    attempt + 1,
                    attempts,
                    info.kind.value,
                )
                await asyncio.sleep(min(2.0, 0.5 * (attempt + 1)))
                continue

            logger.warning(
                "[SCRAPER] descarga_fallo url=%s tipo=%s error=%s",
                url,
                info.kind.value,
                info.message,
            )
            raise

    assert last_exc is not None
    raise last_exc


async def _fetch_and_extract_once(
    url: str,
    *,
    http: httpx.AsyncClient,
    settings: Settings,
    verify: bool,
) -> FetchedDocument:
    """Un intento de descarga y extracción de PDF."""
    if not url_looks_like_pdf(url):
        raise ValueError("Solo se aceptan enlaces a archivos PDF")

    logger.debug("[SCRAPER] fase=descarga url=%s verify_ssl=%s", url, verify)
    headers = {"User-Agent": settings.scraper_user_agent}
    timeout = httpx.Timeout(settings.scraper_fetch_timeout_sec, connect=20.0)

    # httpx no admite ``verify`` por petición en stream(); solo en el constructor del cliente.
    own_client: httpx.AsyncClient | None = None
    client = http
    if not verify:
        own_client = httpx.AsyncClient(
            verify=False,
            timeout=timeout,
            follow_redirects=True,
        )
        client = own_client

    try:
        async with client.stream(
            "GET",
            url,
            headers=headers,
            timeout=timeout if own_client is None else None,
            follow_redirects=True,
        ) as resp:
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
    finally:
        if own_client is not None:
            await own_client.aclose()

    if not raw:
        raise ValueError("Respuesta vacía")

    filename = _guess_filename(url, content_type)
    suf = Path(filename).suffix.lower()
    path_lower = urlparse(url).path.lower()
    if path_lower.endswith(_PDF_HINT):
        filename = Path(filename).stem + ".pdf" if suf != ".pdf" else filename

    ct = (content_type or "").lower()
    if not _looks_like_pdf(raw, ct, path_lower, filename):
        raise ValueError(
            "El enlace no devolvió un PDF válido (solo se indexan archivos PDF normativos)."
        )

    raw = _sanitize_pdf_bytes(raw)
    if not filename.lower().endswith(".pdf"):
        filename = Path(filename).stem + ".pdf"

    try:
        result: ExtractionResult = await extract_document_from_bytes(
            raw, filename, settings=settings
        )
    except ValueError as exc:
        msg = str(exc)
        logger.warning(
            "[SCRAPER] pdf_ilegible url=%s motivo=%s",
            url,
            msg[:200],
        )
        raise ValueError(
            f"PDF ilegible o corrupto ({msg}). Se probará otro enlace."
        ) from exc

    if result.char_count < settings.scraper_min_extracted_chars:
        raise ValueError("Texto extraído del PDF demasiado corto")

    return FetchedDocument(
        url=url,
        text=result.text,
        filename=result.filename,
        extraction_method=result.extraction_method.value,
        char_count=result.char_count,
    )
