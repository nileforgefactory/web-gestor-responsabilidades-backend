import io
import re
from pathlib import Path

from fastapi import UploadFile
from pypdf import PdfReader


def _suffix(path: str) -> str:
    return Path(path).suffix.lower()


async def extract_text_from_upload(upload: UploadFile) -> tuple[str, str]:
    raw = await upload.read()
    if not raw:
        raise ValueError("Archivo vacío")

    filename = upload.filename or "document"
    suf = _suffix(filename)

    if suf == ".pdf":
        reader = PdfReader(io.BytesIO(raw))
        texts: list[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                texts.append(t)
        merged = "\n\n".join(texts).strip()
        if not merged:
            raise ValueError(
                "PDF sin texto seleccionable. Prueba TXT/MD o un PDF exportado desde Word."
            )
        return merged, filename

    if suf in (".txt", ".md", ".markdown", ".rst"):
        return raw.decode("utf-8", errors="replace").strip(), filename

    raise ValueError(
        "Formato no soportado. Usa PDF, TXT o Markdown (.md)."
    )


def extract_title(filename: str) -> str:
    return Path(filename).stem or filename


def derive_document_id_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    slug = re.sub(r"[^\w\-]+", "-", stem, flags=re.UNICODE).strip("-")
    return slug or "documento"
