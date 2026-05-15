"""Extractor unificado: PDF nativo (pypdf) con fallback OCR (Tesseract)."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
_PDF_SUFFIX = ".pdf"
_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst"}


class ExtractionMethod(str, Enum):
    NATIVE = "nativo"
    OCR = "ocr"
    HYBRID = "hibrido"


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    filename: str
    extraction_method: ExtractionMethod
    page_count: int
    char_count: int
    ocr_pages: int = 0
    native_pages: int = 0
    ocr_confidence_avg: float | None = None


def _suffix(filename: str) -> str:
    return Path(filename).suffix.lower()


def _page_separator(page_num: int) -> str:
    return f"\n\n--- Página {page_num} ---\n\n"


class DocumentExtractor:
    def __init__(
        self,
        *,
        ocr_enabled: bool = True,
        ocr_lang: str = "spa",
        ocr_dpi: int = 200,
        min_chars_per_page: int = 50,
    ) -> None:
        self.ocr_enabled = ocr_enabled
        self.ocr_lang = ocr_lang
        self.ocr_dpi = ocr_dpi
        self.min_chars_per_page = min_chars_per_page

    def extract_from_bytes(self, raw: bytes, filename: str) -> ExtractionResult:
        if not raw:
            raise ValueError("Archivo vacío")

        suf = _suffix(filename)
        if suf in _TEXT_SUFFIXES:
            text = raw.decode("utf-8", errors="replace").strip()
            return self._result(text, filename, ExtractionMethod.NATIVE, page_count=1)

        if suf in _IMAGE_SUFFIXES:
            return self._extract_image(raw, filename)

        if suf == _PDF_SUFFIX:
            return self._extract_pdf(raw, filename)

        raise ValueError(
            "Formato no soportado. Usa PDF, TXT, Markdown o imagen (PNG, JPG, TIFF)."
        )

    def _result(
        self,
        text: str,
        filename: str,
        method: ExtractionMethod,
        *,
        page_count: int,
        ocr_pages: int = 0,
        native_pages: int = 0,
        ocr_confidence_avg: float | None = None,
    ) -> ExtractionResult:
        merged = text.strip()
        if not merged:
            raise ValueError(
                "No se pudo extraer texto del documento. "
                "Verifica que el archivo tenga contenido legible o habilita OCR."
            )
        return ExtractionResult(
            text=merged,
            filename=filename,
            extraction_method=method,
            page_count=page_count,
            char_count=len(merged),
            ocr_pages=ocr_pages,
            native_pages=native_pages,
            ocr_confidence_avg=ocr_confidence_avg,
        )

    def _extract_image(self, raw: bytes, filename: str) -> ExtractionResult:
        if not self.ocr_enabled:
            raise ValueError(
                "Imagen sin OCR habilitado. Configura OCR_ENABLED=true o usa PDF/TXT."
            )
        text, conf = self._ocr_image_bytes(raw)
        return self._result(
            text,
            filename,
            ExtractionMethod.OCR,
            page_count=1,
            ocr_pages=1,
            ocr_confidence_avg=conf,
        )

    def _extract_pdf(self, raw: bytes, filename: str) -> ExtractionResult:
        reader = PdfReader(io.BytesIO(raw))
        num_pages = len(reader.pages)
        if num_pages == 0:
            raise ValueError("PDF sin páginas")

        page_text: dict[int, str] = {}
        pages_needing_ocr: list[int] = []
        native_count = 0

        for i, page in enumerate(reader.pages, start=1):
            native = (page.extract_text() or "").strip()
            if len(native) >= self.min_chars_per_page:
                page_text[i] = native
                native_count += 1
            else:
                pages_needing_ocr.append(i)

        if not pages_needing_ocr:
            merged = "".join(
                _page_separator(p) + page_text[p] for p in range(1, num_pages + 1)
            )
            return self._result(
                merged,
                filename,
                ExtractionMethod.NATIVE,
                page_count=num_pages,
                native_pages=native_count,
            )

        if not self.ocr_enabled:
            if page_text:
                merged = "".join(
                    _page_separator(p) + page_text[p]
                    for p in sorted(page_text)
                )
                return self._result(
                    merged,
                    filename,
                    ExtractionMethod.NATIVE,
                    page_count=num_pages,
                    native_pages=native_count,
                )
            raise ValueError(
                "PDF sin texto seleccionable y OCR deshabilitado. "
                "Activa OCR_ENABLED o usa un PDF exportado desde Word."
            )

        ocr_by_page, conf_avg = self._ocr_pdf_pages(raw, pages_needing_ocr)
        ocr_count = 0
        for p in pages_needing_ocr:
            ocr_text = ocr_by_page.get(p, "").strip()
            if ocr_text:
                page_text[p] = ocr_text
                ocr_count += 1
            elif p not in page_text:
                page_text[p] = ""

        merged = "".join(
            _page_separator(p) + page_text.get(p, "")
            for p in range(1, num_pages + 1)
        ).strip()

        if not merged.replace("-", "").strip():
            raise ValueError(
                "PDF sin texto extraíble. Comprueba calidad del escaneo o idioma OCR (spa)."
            )

        if ocr_count == num_pages:
            method = ExtractionMethod.OCR
        elif ocr_count > 0:
            method = ExtractionMethod.HYBRID
        else:
            method = ExtractionMethod.NATIVE

        return ExtractionResult(
            text=merged,
            filename=filename,
            extraction_method=method,
            page_count=num_pages,
            char_count=len(merged),
            ocr_pages=ocr_count,
            native_pages=native_count,
            ocr_confidence_avg=conf_avg,
        )

    def _ocr_pdf_pages(
        self,
        raw: bytes,
        page_numbers: list[int],
    ) -> tuple[dict[int, str], float | None]:
        from pdf2image import convert_from_bytes

        if not page_numbers:
            return {}, None

        images = convert_from_bytes(
            raw,
            dpi=self.ocr_dpi,
            first_page=min(page_numbers),
            last_page=max(page_numbers),
        )
        page_set = set(page_numbers)
        confidences: list[float] = []
        out: dict[int, str] = {}

        start = min(page_numbers)
        for offset, img in enumerate(images):
            page_num = start + offset
            if page_num not in page_set:
                continue
            text, conf = self._ocr_pil_image(img)
            if text.strip():
                out[page_num] = text.strip()
            if conf is not None:
                confidences.append(conf)

        avg = sum(confidences) / len(confidences) if confidences else None
        return out, avg

    def _ocr_image_bytes(self, raw: bytes) -> tuple[str, float | None]:
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        return self._ocr_pil_image(img)

    def _ocr_pil_image(self, img) -> tuple[str, float | None]:
        import pytesseract

        data = pytesseract.image_to_data(
            img,
            lang=self.ocr_lang,
            output_type=pytesseract.Output.DICT,
        )
        confs = [
            float(c)
            for c in data.get("conf", [])
            if str(c).lstrip("-").isdigit() and float(c) >= 0
        ]
        text = pytesseract.image_to_string(img, lang=self.ocr_lang)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        avg = sum(confs) / len(confs) if confs else None
        return text, avg


def get_document_extractor_from_settings(settings) -> DocumentExtractor:
    return DocumentExtractor(
        ocr_enabled=settings.ocr_enabled,
        ocr_lang=settings.ocr_lang,
        ocr_dpi=settings.ocr_dpi,
        min_chars_per_page=settings.ocr_min_chars_per_page,
    )
