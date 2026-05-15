"""Estrategias de chunking: fijo y adaptativo (Sprint 2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ChunkStrategy(str, Enum):
    FIXED = "fixed"
    ADAPTIVE = "adaptive"


class ChunkProfile(str, Enum):
    FIXED = "fixed"
    DEFAULT = "default"
    LEGAL_DENSE = "legal_dense"
    NARRATIVE = "narrative"
    OCR_NOISY = "ocr_noisy"


_PROFILE_SIZES: dict[ChunkProfile, tuple[int, int]] = {
    ChunkProfile.OCR_NOISY: (480, 95),
    ChunkProfile.LEGAL_DENSE: (580, 105),
    ChunkProfile.NARRATIVE: (1050, 175),
    ChunkProfile.DEFAULT: (700, 120),
}

_BOUNDARY_PATTERNS = (
    r"\n\n+",
    r"\n(?=Art(?:ículo|\.)?\s*\d+)",
    r"\n(?=\d+\.\s)",
    r"\n(?=\d+\.\d+\s)",
    r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])",
)

_MAX_CHUNK = 2000
_MIN_CHUNK = 200


@dataclass(frozen=True)
class ChunkingResult:
    chunks: list[str]
    strategy: ChunkStrategy
    profile: ChunkProfile
    chunk_size: int
    chunk_overlap: int


def chunk_text_by_chars(content: str, chunk_size: int, overlap: int) -> list[str]:
    text = content.strip()
    if not text:
        return []
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 4)
    size = min(max(chunk_size, _MIN_CHUNK), _MAX_CHUNK)
    ov = min(overlap, size // 2)
    chunks: list[str] = []
    step = size - ov
    pos = 0
    length = len(text)
    while pos < length:
        end = min(pos + size, length)
        piece = text[pos:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        pos += step
    return chunks


def _detect_profile(text: str, extraction_method: str | None) -> ChunkProfile:
    if extraction_method in ("ocr", "hibrido"):
        return ChunkProfile.OCR_NOISY

    sample = text[:120_000]
    legal_hits = len(
        re.findall(
            r"\b(?:Ley|Decreto|Resolución|Ordenanza|Acuerdo)\s+\d+|Art(?:ículo|\.)?\s*\d+",
            sample,
            flags=re.IGNORECASE,
        )
    )
    density = legal_hits / max(len(sample) / 4000, 1.0)
    if legal_hits >= 6 and density >= 1.2:
        return ChunkProfile.LEGAL_DENSE
    if len(sample) > 18_000:
        return ChunkProfile.NARRATIVE
    return ChunkProfile.DEFAULT


def _split_with_boundaries(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Intenta cortar en fronteras semánticas antes que a mitad de frase."""
    if len(text) <= chunk_size:
        stripped = text.strip()
        return [stripped] if stripped else []

    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        hard_end = min(start + chunk_size, length)
        if hard_end >= length:
            piece = text[start:].strip()
            if piece:
                chunks.append(piece)
            break

        window = text[start:hard_end]
        cut = -1
        for pattern in _BOUNDARY_PATTERNS:
            for match in re.finditer(pattern, window):
                pos = match.start()
                if pos > chunk_size * 0.35:
                    cut = max(cut, pos)
            if cut > 0:
                break

        if cut <= 0:
            cut = len(window)

        piece = text[start : start + cut].strip()
        if piece:
            chunks.append(piece)

        if start + cut >= length:
            break
        start = max(start + cut - overlap, start + 1)

    return chunks


def chunk_document(
    content: str,
    *,
    strategy: ChunkStrategy | str = ChunkStrategy.ADAPTIVE,
    chunk_size: int = 700,
    chunk_overlap: int = 120,
    extraction_method: str | None = None,
) -> ChunkingResult:
    strat = ChunkStrategy(str(strategy).lower())
    text = content.strip()
    if not text:
        return ChunkingResult(
            chunks=[],
            strategy=strat,
            profile=ChunkProfile.DEFAULT,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    if strat == ChunkStrategy.FIXED:
        size = min(max(chunk_size, _MIN_CHUNK), _MAX_CHUNK)
        ov = min(chunk_overlap, size // 2)
        chunks = chunk_text_by_chars(text, size, ov)
        return ChunkingResult(
            chunks=chunks,
            strategy=strat,
            profile=ChunkProfile.FIXED,
            chunk_size=size,
            chunk_overlap=ov,
        )

    profile = _detect_profile(text, extraction_method)
    size, ov = _PROFILE_SIZES[profile]
    chunks = _split_with_boundaries(text, size, ov)
    if not chunks:
        chunks = chunk_text_by_chars(text, size, ov)

    return ChunkingResult(
        chunks=chunks,
        strategy=strat,
        profile=profile,
        chunk_size=size,
        chunk_overlap=ov,
    )
