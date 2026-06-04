"""Extracción de texto con fallback OCR para PDFs escaneados e imágenes."""

from app.slices.ocr.extractor import DocumentExtractor, ExtractionMethod, ExtractionResult

__all__ = [
    "DocumentExtractor",
    "ExtractionMethod",
    "ExtractionResult",
]
