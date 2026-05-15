import asyncio
import re
from pathlib import Path

from fastapi import UploadFile

from app.core.config import Settings, get_settings
from app.slices.ocr.extractor import DocumentExtractor, ExtractionResult, get_document_extractor_from_settings


def _extractor(settings: Settings | None = None) -> DocumentExtractor:
    return get_document_extractor_from_settings(settings or get_settings())


async def extract_text_from_upload(
    upload: UploadFile,
    *,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """Compatibilidad RAG: devuelve (texto, nombre_archivo)."""
    result = await extract_document_from_upload(upload, settings=settings)
    return result.text, result.filename


async def extract_document_from_bytes(
    raw: bytes,
    filename: str,
    *,
    settings: Settings | None = None,
) -> ExtractionResult:
    extractor = _extractor(settings)
    return await asyncio.to_thread(extractor.extract_from_bytes, raw, filename)


async def extract_document_from_upload(
    upload: UploadFile,
    *,
    settings: Settings | None = None,
) -> ExtractionResult:
    raw = await upload.read()
    filename = upload.filename or "document"
    return await extract_document_from_bytes(raw, filename, settings=settings)


def extract_title(filename: str) -> str:
    return Path(filename).stem or filename


def derive_document_id_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    slug = re.sub(r"[^\w\-]+", "-", stem, flags=re.UNICODE).strip("-")
    return slug or "documento"
