# Sprint 2 — Chunking dinámico

**Estado:** Implementado  
**Objetivo:** Ajustar tamaño y solapamiento de chunks según tipo de documento y calidad OCR para mejorar recuperación RAG y contexto de agentes.

---

## Alcance entregado

| ID | Tarea | Ubicación |
|----|--------|-----------|
| 2.1 | Módulo de estrategias `fixed` / `adaptive` | `app/slices/rag/chunking/strategy.py` |
| 2.2 | Perfiles: `ocr_noisy`, `legal_dense`, `narrative`, `default` | mismo archivo |
| 2.3 | Cortes en fronteras (párrafos, artículos, numeración) | `_split_with_boundaries` |
| 2.4 | Integración en ingesta RAG | `app/slices/rag/service.py` |
| 2.5 | Parámetro `chunk_strategy` en API | `ingest-text`, `ingest-file`, `ingest-files` |
| 2.6 | Metadatos en respuesta | `chunk_strategy`, `chunk_profile`, tamaños aplicados |

---

## Estrategias

| Valor | Comportamiento |
|-------|----------------|
| `fixed` | Usa `chunk_size` y `chunk_overlap` del formulario tal cual |
| `adaptive` | Detecta perfil y aplica tamaños optimizados (default en Docker) |

### Perfiles adaptativos

| Perfil | Cuándo | chunk_size × overlap (aprox.) |
|--------|--------|-------------------------------|
| `ocr_noisy` | Extracción `ocr` o `hibrido` | 480 × 95 |
| `legal_dense` | Muchas referencias Ley/Decreto/Art. | 580 × 105 |
| `narrative` | Texto largo (>18k chars) | 1050 × 175 |
| `default` | Resto | 700 × 120 |

Límites globales: mínimo 200, máximo 2000 caracteres por chunk.

---

## API

### `POST /api/v1/rag/ingest-text` (JSON)

```json
{
  "collection_id": "plan_demo",
  "document_id": "plan-2024",
  "content": "...",
  "chunk_strategy": "adaptive",
  "chunk_size": 700,
  "chunk_overlap": 120
}
```

Con `adaptive`, `chunk_size` / `chunk_overlap` actúan como referencia; el perfil puede sobreescribirlos.

### `POST /api/v1/rag/ingest-file` / `ingest-files`

Campo form: `chunk_strategy` = `fixed` | `adaptive` (default `adaptive`).

### Respuesta ampliada

```json
{
  "collection_id": "plan_demo",
  "document_id": "plan-2024",
  "chunks_indexed": 42,
  "chunk_strategy": "adaptive",
  "chunk_profile": "legal_dense",
  "chunk_size_applied": 580,
  "chunk_overlap_applied": 105
}
```

---

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DEFAULT_CHUNK_STRATEGY` | `adaptive` | Estrategia por defecto si no se envía en la petición |

---

## Criterios de aceptación

- [ ] PDF escaneado (`ocr`) indexa con `chunk_profile=ocr_noisy`
- [ ] Documento con muchas leyes usa perfil `legal_dense`
- [ ] `chunk_strategy=fixed` respeta tamaños del formulario
- [ ] Ingesta masiva propaga estrategia y método de extracción

---

## Siguiente paso

[Sprint 3 — Agentes y análisis de documento](./SPRINT_3.md)
