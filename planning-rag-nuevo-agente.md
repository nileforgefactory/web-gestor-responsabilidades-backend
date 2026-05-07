# Planning técnico para iniciar un nuevo agente (basado en `llm/src`)

## Objetivo

Este documento resume cómo funciona el sistema actual en `src/` para reutilizar sus patrones en un nuevo proyecto. Incluye:

1. Proceso de RAG
2. Modelos de RAG
3. Articulación con Qdrant
4. Vectorización de datos y consultas
5. Colecciones (qué son y cómo funcionan)
6. Proceso modelo de ingesta para alimentar agentes
7. Modelos/patrones de scraping
8. Modelos de análisis de documentos
9. Procesamiento de documentos
10. Maqueta en Markdown para arrancar desde un nuevo agente

---

## 0) Plan de demo hoy (Local + Docker + sin APIs externas)

### Meta de la demo (hoy)

Demostrar en vivo que el agente:

1. Procesa documentos locales (PDF/TXT/Markdown).
2. Construye embeddings localmente.
3. Indexa y recupera evidencia desde Qdrant.
4. Responde preguntas usando solo contexto de los documentos.
5. Opera 100% local, orquestado desde Docker Compose.

### Alcance MVP de demo

- **Incluir**:
  - Ingesta de al menos 3 documentos reales.
  - Chunking + embeddings + upsert en Qdrant.
  - Endpoint de consulta RAG con citas de fuente.
  - UI mínima (CLI o endpoint HTTP) para preguntar/responder.
- **Excluir por hoy**:
  - Scraping web productivo.
  - Reranking avanzado.
  - Memoria conversacional compleja.
  - Multi-tenant completo.

### Arquitectura objetivo para hoy (todo local)

- `api` (FastAPI): expone endpoints de ingesta y consulta.
- `worker` (Python): procesa documentos en background.
- `qdrant` (Vector DB): almacena chunks y metadata.
- `ollama` (LLM + embeddings locales):
  - Modelo de chat sugerido: `llama3.1:8b-instruct` (o equivalente disponible).
  - Modelo de embeddings sugerido: `nomic-embed-text`.
- `minio` (opcional): almacenamiento de archivos si se quiere simular flujo productivo.

### Docker Compose mínimo sugerido

Proyecto Compose con nombre **`api-rag`** (prefijo visible en Docker Desktop) y Swagger en **`/docs`**.

Servicios recomendados:

1. `qdrant` con volumen persistente.
2. `ollama` con volumen de modelos.
3. `api` montando código local.
4. `worker` montando código local (opcional; en el repo actual ingesta/consulta viven en el servicio API).

Variables de entorno mínimas:

- `VECTOR_DB_URL=http://qdrant:6333`
- `OLLAMA_BASE_URL=http://ollama:11434`
- `EMBEDDING_MODEL=nomic-embed-text`
- `CHAT_MODEL=llama3.1:8b-instruct`
- `RAG_TOP_K=5`
- `RAG_SCORE_THRESHOLD=0.25`

### Flujo E2E de la demo

1. Subir documentos a endpoint `/ingest`.
2. Worker extrae texto y lo normaliza.
3. Worker realiza chunking (ej. 700 chars, overlap 120).
4. Worker genera embeddings con Ollama.
5. Worker indexa en Qdrant con metadata (`document_id`, `chunk_id`, `source`, `collection_id`).
6. Usuario consulta `/ask`.
7. API embebe query, busca top-k en Qdrant, arma contexto.
8. API invoca modelo local de chat y responde con citas.

### Contrato mínimo de respuesta (obligatorio en demo)

Toda respuesta debe devolver:

- `answer`: texto final.
- `citations`: lista de fuentes usadas.
- `confidence`: score agregado simple.
- `used_chunks`: IDs de chunks recuperados.

Si no hay evidencia suficiente (por threshold), responder:

- `answer`: "No tengo evidencia suficiente en los documentos cargados."
- `citations`: `[]`

### Criterio de éxito de demo (hoy)

- El sistema levanta con `docker compose up`.
- Se pueden ingestar documentos sin errores.
- 5/5 preguntas de prueba responden con al menos 1 cita válida.
- No usa OpenAI/Azure/u otras APIs externas.
- Reinicio de contenedores conserva índice (volumen persistente).

### Plan operativo en bloques (3-4 horas)

1. **Bloque 1 (Infra, 45-60 min)**  
   Levantar compose, validar salud de `qdrant` y `ollama`, descargar modelos.
2. **Bloque 2 (Ingesta, 60-90 min)**  
   Implementar/fijar pipeline único de ingesta local y registrar metadata.
3. **Bloque 3 (Consulta RAG, 60-90 min)**  
   Endpoint `/ask` con recuperación + prompt + respuesta con citas.
4. **Bloque 4 (Ensayo demo, 30 min)**  
   Ejecutar script de preguntas y validar criterio de éxito.

### Script de prueba recomendado para la demo

Preparar un archivo `demo_questions.md` con:

- 5 preguntas respondibles por los documentos.
- 2 preguntas trampa (sin evidencia) para validar fallback.

### Riesgos de última milla y mitigación rápida

1. **Modelo no descargado a tiempo**  
   Mitigación: pre-pull de modelos antes del ensayo (`ollama pull ...`).
2. **Latencia alta en CPU**  
   Mitigación: bajar tamaño de contexto y top-k; usar modelo chat más liviano.
3. **Extracción pobre de PDF complejo**  
   Mitigación: usar documentos limpios para la demo inicial + fallback TXT/MD.

---

## 1) Cómo se realiza el proceso de RAG

### Flujo principal observado

- El flujo de ejecución del chatbot pasa por `src/domains/chatbots/usecases/execute_chatbot.py`.
- Antes de invocar el LLM, se carga contexto RAG mediante `LoadRagContextForChatbotUseCase` en `src/domains/chatbots/usecases/load_rag_context_for_chatbot.py`.
- El caso de uso arma la consulta efectiva y resuelve las colecciones objetivo.
- Existen dos rutas:
  - **RAG tradicional**: usa `RagManager.search_in_collections(...)`.
  - **RAG con thinking**: usa `RagThinkingClient.search(...)` hacia microservicio.
- Además, puede mezclar memoria conversacional (`SearchMemoriesUsecase`) y variables de entrada como pseudo-documentos.
- Finalmente, devuelve documentos (`RagSearchTO.documents`) que se inyectan al prompt/contexto del `LLM_Manager`.

### Resultado práctico

El RAG actual no es solo “buscar y responder”; primero compone contexto con reglas de negocio (colecciones, memorias, variables) y luego lo entrega al motor LLM.

---

## 2) Modelos de RAG identificados

### Embeddings

- En `src/models/llm.py` se usa `LLM.get_embedding(...)`, con default histórico `text-embedding-ada-002`.
- En `src/utils/embeddings.py` (`get_embed_query`) se soporta OpenAI y Azure OpenAI.
- En nodos del orquestador se observan variantes:
  - `text-embedding-3-small`
  - `text-embedding-3-large`

### Reranking

- `src/models/document.py` incluye reranking con CrossEncoder para reordenar resultados relevantes.

### Implicación de diseño

Hay heterogeneidad de modelos de embedding. Para un nuevo proyecto conviene estandarizar (modelo, dimensiones, costo/latencia) antes de pasar a producción.

---

## 3) Articulación con Qdrant

### Capa de acceso

- Cliente y utilidades en `src/db/vector_db.py`:
  - Cliente singleton async/sync
  - Creación de colección si no existe (`size=1536`, distancia cosine)
  - Búsquedas vectoriales y operaciones de apoyo.

### Colecciones de contenido observadas

- `documents_content`
- `Faq`
- `texts_content`
- `websites_content`
- Otras de soporte: `memories`, `contextual_documents_content`, `search`.

### Operaciones típicas

- Upsert de chunks embebidos con payload de metadata.
- Delete por filtros de metadata.
- Scroll/filter para auditoría/reindex.
- Índices de payload para campos de filtro como `collection_id`.

---

## 4) Vectorización de datos y consultas

### Datos

- Los contenidos (documentos, FAQs, textos, websites) se transforman en chunks semánticos.
- Cada chunk se vectoriza y se almacena en Qdrant con metadata trazable (IDs de colección, recurso, etc.).

### Consultas

- La query del usuario se convierte en embedding (`get_embed_query(...)`).
- Se ejecuta búsqueda vectorial por colección + filtros.
- Se aplica score threshold, top-k y en algunos casos reranking.

### Recomendación para nuevo proyecto

Definir desde el inicio:
- Estrategia de chunking (longitud, overlap, semántico vs fijo).
- Esquema de metadata mínimo obligatorio.
- Política de reranking (cuándo sí / cuándo no).

---

## 5) Qué son y cómo funcionan las colecciones

### Concepto funcional

Una colección es la frontera lógica para agrupar conocimiento (tenancy, dominio o contexto) y filtrar recuperación RAG.

### Ciclo de vida

- Creación / actualización / eliminación de colecciones.
- Asignación de activos (docs, textos, FAQs, websites) a colecciones.
- Migraciones entre esquemas antiguos y nuevos.

### Importancia

Las colecciones son la unidad clave de gobierno del conocimiento: determinan qué puede recuperar cada agente/chatbot.

---

## 6) Proceso modelo de ingesta para alimentar agentes

## Pipeline recomendado (basado en el repositorio)

1. **Recepción del contenido** (archivo, URL, webhook, API interna).
2. **Extracción de texto** por tipo MIME.
3. **Normalización** (limpieza, idioma, deduplicación básica).
4. **Chunking semántico**.
5. **Embeddings** por chunk.
6. **Indexación** en Qdrant (+ opcional Elasticsearch).
7. **Registro de metadata** en DB transaccional.
8. **Sincronización de retrievers** (si aplica microservicio RAG).
9. **Observabilidad** (estado, métricas, errores, reintentos).

### Componentes reutilizables existentes

- `LoadRagContextForChatbotUseCase` para ensamblar contexto de agente/chatbot.
- Indexadores como `TextRetrievalIndexer` y `FaqRetrievalIndexer`.
- Nodos de orquestador para chunking, guardado de embeddings y búsquedas.

---

## 7) Modelos/patrones de scrapper para barrer la red

### Patrón principal detectado

- Flujo de scraping vía webhook en `src/controllers/scraping_integration.py`.
- Consumo de artefactos scrapeados desde MinIO.
- Alta/actualización de `website`.
- Indexación a motores de recuperación (Qdrant/Elastic) y sincronización de retrievers.

### Orquestación de websites

- `src/models/website.py` contiene lógica de ejecución de flujo, descubrimiento de links y clasificación.

### Recomendación

Para un nuevo sistema, desacoplar scraping en un worker/servicio independiente con contrato de webhook idempotente.

---

## 8) Modelos de análisis de documentos

En `src/domains/organization_intelligence/analyzers/` se observa una capa de análisis para:

- Proponer ubicación/uso del documento.
- Generar sugerencias premium basadas en contenido y activos existentes.
- Detectar oportunidades de procesos/automatización.

Complementa la recuperación RAG con una capa de decisión.

---

## 9) Procesamiento de documentos

### Flujo observado

- Extracción por tipo de archivo: `ExtractDocumentContentUseCase`.
- Preparación del contenido para chunking/vectorización.
- Indexación y sincronización de retrievers.
- Soporte de re-procesamiento, eliminación y reindexación.

### Consideraciones de ingeniería

- Idempotencia por documento y versión.
- Limpieza completa de índices al borrar/reprocesar.
- Trazabilidad entre entidad documental y chunks vectorizados.

---

## 10) Maqueta en Markdown para iniciar desde un nuevo agente

Usar esta plantilla como base para el nuevo proyecto:

```markdown
# Nuevo Agente RAG - Plan de Inicio

## 1. Objetivo y alcance
- Problema a resolver:
- Tipo de usuarios:
- Casos de uso iniciales (MVP):
- No-objetivos:

## 2. Arquitectura base
- API principal:
- Worker de ingesta:
- Base transaccional:
- Vector DB (Qdrant):
- Opcional búsqueda textual (Elastic):
- Servicio LLM:

## 3. Modelo de conocimiento
- Entidades: Documento, FAQ, Texto, Website
- Colecciones: estrategia de segmentación
- Esquema de metadata obligatorio

## 4. Pipeline de ingesta
- Fuentes de entrada:
- Extracción por formato:
- Chunking:
- Embeddings:
- Indexación:
- Reintentos e idempotencia:

## 5. Pipeline de recuperación (RAG)
- Query preprocessing:
- Búsqueda vectorial:
- Filtros por colección:
- Reranking:
- Construcción de contexto final:

## 6. Integración con agentes
- Cómo se carga contexto RAG en el agente:
- Memoria conversacional:
- Variables de contexto:
- Prompting strategy:

## 7. Scraping web
- Fuentes objetivo:
- Método de scraping:
- Frecuencia:
- Validación y limpieza:
- Ingesta post-scraping:

## 8. Análisis documental
- Clasificación de documentos:
- Detección de intención/tema:
- Recomendaciones de asignación a colecciones/agentes:

## 9. Seguridad y gobierno
- Control de acceso por organización:
- Manejo de secretos:
- Retención/eliminación de datos:

## 10. Observabilidad
- Métricas clave:
- Logs:
- Trazas:
- Alertas:

## 11. Testing
- Unit tests por capa:
- Integration tests de ingesta/RAG:
- Datos sintéticos de prueba:

## 12. Roadmap (90 días)
### Fase 1 (Semanas 1-3)
- Infraestructura mínima + primer pipeline de ingesta
### Fase 2 (Semanas 4-6)
- Retrieval robusto + calidad de respuesta
### Fase 3 (Semanas 7-9)
- Scraping + análisis documental
### Fase 4 (Semanas 10-12)
- Hardening, seguridad, observabilidad, costos
```

---

## Riesgos y decisiones clave para tu nuevo proyecto

1. **Estandarización de embeddings**: evitar mezclar modelos sin estrategia.
2. **Contrato de metadata**: definirlo al inicio para no romper filtros.
3. **Ruta RAG única o dual**: decidir si habrá “tradicional + thinking”.
4. **Costo/latencia**: balancear reranking y tamaño de contexto.
5. **Separación de responsabilidades**: ingesta asíncrona desacoplada de serving.

---

## Próximos pasos sugeridos

1. Elegir un único modelo de embedding para MVP.
2. Definir contrato de `collection` y metadata (v1).
3. Implementar pipeline de ingesta mínimo end-to-end con un tipo de documento.
4. Implementar loader de contexto para agente con top-k y score threshold.
5. Medir calidad inicial (relevancia) antes de añadir complejidad.

---

## 11) Dudas abiertas (para resolver antes de implementar)

Estas dudas deben responderse explícitamente; de lo contrario, el proyecto tiende a desviarse.

### Producto y alcance

1. ¿Cuál es el objetivo principal del agente en negocio (soporte, ventas, legal, operaciones)?
2. ¿Cuál es el nivel de criticidad de respuesta (informativo vs decisiones de alto riesgo)?
3. ¿Cuál es el canal inicial (API, webchat, WhatsApp, interno)?
4. ¿Qué idiomas debe soportar y con qué prioridad?

### Datos y conocimiento

5. ¿Cuáles son las fuentes oficiales de verdad (documentos internos, web pública, CRM, ERP)?
6. ¿Con qué frecuencia cambia el contenido y cada cuánto se debe reindexar?
7. ¿Qué calidad mínima de OCR/extracción es aceptable?
8. ¿Qué volumen de datos inicial y proyectado se espera (chunks, consultas/día)?

### Seguridad y compliance

9. ¿Qué restricciones legales aplican (PII, contratos, confidencialidad, residencia de datos)?
10. ¿Quién puede consultar qué colecciones (RBAC por organización/equipo)?
11. ¿Qué política de retención y borrado aplica para documentos y embeddings?

### Operación técnica

12. ¿Se necesita ruta dual de RAG (tradicional + thinking) desde MVP o solo una?
13. ¿Cuál es el presupuesto mensual máximo de inferencia/embeddings?
14. ¿Qué SLA de latencia y disponibilidad debe cumplirse?
15. ¿Qué observabilidad mínima se requiere desde día 1?

---

## 12) Recomendaciones accionables del proceso

### Recomendaciones de arquitectura

1. **Empezar simple**: una sola ruta RAG (tradicional) en MVP; añadir thinking cuando haya métricas base.
2. **Modelo de embedding único**: usar un solo modelo y una sola dimensión por entorno.
3. **Contrato de metadata versionado**: definir `metadata_schema_version` para migrar sin romper búsquedas.
4. **Ingesta asíncrona desacoplada**: API solo recibe/consulta estado; worker procesa extracción y vectorización.
5. **Colecciones como límite de autorización**: nunca recuperar contenido fuera de colecciones permitidas.

### Recomendaciones de calidad de respuesta

6. **Umbral de confianza**: si score bajo, responder con “no tengo evidencia suficiente”.
7. **Citas de fuente**: toda respuesta RAG debe incluir origen (documento/url/chunk).
8. **Reranking selectivo**: habilitar solo en queries complejas para controlar costo/latencia.
9. **Top-k adaptativo**: no fijo global; ajustar por tipo de consulta y longitud del prompt.

### Recomendaciones de operación

10. **Idempotencia obligatoria** en ingesta (clave por `document_id + version_hash`).
11. **Borrado consistente**: delete transaccional lógico + limpieza física de índices.
12. **Playbooks de reindexado**: runbooks explícitos para recuperación ante fallos.
13. **Métricas obligatorias**: recall aparente, latencia p95, costo por 1k consultas, tasa de “sin contexto”.

---

## 13) Decisiones mínimas de diseño (checklist)

Marcar cada punto como `DECIDIDO` antes de iniciar desarrollo fuerte.

- [x] Embedding model elegido: `nomic-embed-text` (local en Ollama).
- [x] Dimensión vectorial elegida: definir automáticamente según modelo de embedding (sin hardcode para evitar mismatch).
- [x] Estrategia de chunking (semántico/fijo/híbrido): fijo para MVP demo (`700` chars, `120` overlap).
- [x] Top-k por defecto: `5`.
- [x] Score threshold por defecto: `0.25` (ajustable tras pruebas).
- [x] Política de reranking: desactivado en demo inicial (activar solo si baja precisión).
- [x] Esquema de metadata v1 aprobado: `collection_id`, `document_id`, `chunk_id`, `source`, `title`, `ingested_at`.
- [x] Política de colecciones (ownership + permisos): colección única `demo_local` para hoy.
- [x] Estrategia de reindexado: reindexado total por documento (`document_id`) al reingestar.
- [x] Estrategia de observabilidad: logs estructurados + endpoint health + métricas básicas de latencia.
- [x] Política de retención/borrado: borrado lógico en DB y físico por filtro en Qdrant.
- [x] Criterio de “respuesta sin evidencia”: responder explícitamente que no hay evidencia en documentos cargados.

---

## 14) Capacidad objetivo del agente (definición operativa)

Al finalizar la primera versión, el agente debe poder:

1. Recibir consultas en lenguaje natural.
2. Determinar colecciones permitidas para el usuario.
3. Generar embedding de consulta y recuperar evidencia relevante.
4. Armar contexto con evidencias + memoria (si aplica).
5. Responder con trazabilidad de fuentes.
6. Negarse correctamente cuando no exista evidencia suficiente.
7. Registrar métricas y eventos para auditoría.

### Criterios de aceptación funcional

- 90% de consultas de prueba con al menos una fuente válida adjunta.
- p95 de latencia bajo objetivo definido por negocio.
- 100% de respuestas con fuente en modo “RAG obligatorio”.
- 0 fugas de información entre colecciones no autorizadas.

---

## 15) Plan de implementación afinado (MVP a producción)

### Fase A - Fundaciones (Semana 1)

- Definir ADRs técnicas (embeddings, metadata, chunking, seguridad).
- Levantar servicios mínimos: API, worker de ingesta, Qdrant, storage.
- Implementar contrato de colección + permisos.

**Entrega:** arquitectura ejecutable base + decisiones congeladas v1.

### Fase B - Ingesta funcional (Semanas 2-3)

- Pipeline E2E para un tipo documental prioritario (ej. PDF).
- Extracción, chunking, embeddings, indexación y estado de procesamiento.
- Endpoint de estado por documento/lote.

**Entrega:** contenido ingestado consultable en Qdrant con trazabilidad.

### Fase C - Retrieval y respuesta (Semanas 4-5)

- Query embedding + búsqueda por colección + filtros.
- Constructor de contexto y respuesta con citas.
- Política de fallback sin evidencia.

**Entrega:** agente responde con evidencia verificable.

### Fase D - Calidad y endurecimiento (Semanas 6-8)

- Evaluaciones de calidad (set de preguntas reales).
- Ajustes de top-k, threshold, chunking y prompts.
- Observabilidad completa + runbooks de incidentes.

**Entrega:** versión estable lista para piloto.

---

## 16) Prompt maestro para otra chat (ejecución guiada)

Usa este bloque para que otra chat implemente el proyecto de forma ordenada:

```markdown
Eres un agente técnico senior. Debes construir un backend RAG productivo siguiendo este documento.

Objetivo:
- Implementar un agente que responda con evidencia recuperada desde Qdrant, respetando permisos por colección.

Reglas de ejecución:
1. No inventes arquitectura fuera de este documento sin justificar trade-off.
2. Antes de codificar cada módulo, confirma decisiones pendientes del checklist.
3. Entrega por incrementos funcionales (fundación, ingesta, retrieval, hardening).
4. Incluye tests unitarios e integración mínimos por incremento.
5. Cada respuesta debe listar: archivos creados/modificados, riesgos, pendientes.

Entregables obligatorios:
- Contrato de metadata v1
- Pipeline de ingesta E2E
- Loader de contexto RAG
- Respuesta con citas
- Métricas base y dashboard mínimo
- Runbook de reindexado y borrado

Criterios de calidad:
- Sin fugas entre colecciones
- Sin respuestas sin fuente en modo RAG obligatorio
- Latencia y costo reportados
```

---

## 17) Plantilla de ADRs (arquitectura) para evitar ambigüedad

Crear un archivo por decisión en `plans/adrs/`.

```markdown
# ADR-00X: <titulo breve>

## Contexto
Qué problema resuelve esta decisión.

## Decisión
Qué se elige exactamente.

## Opciones evaluadas
- Opción A:
- Opción B:
- Opción C:

## Consecuencias
Impacto técnico, costo, latencia, riesgo.

## Estado
Propuesta | Aprobada | Rechazada | Reemplazada
```

---

## 18) Riesgos no funcionales y mitigaciones

1. **Deriva de calidad en respuestas**  
   Mitigación: set de evaluación periódica + revisión de top-k/threshold.

2. **Incremento no controlado de costos**  
   Mitigación: límites por tenant, caché de embeddings de consulta, reporting semanal.

3. **Inconsistencia entre DB y Qdrant**  
   Mitigación: reconciliador nocturno + jobs de reparación idempotentes.

4. **Pérdida de trazabilidad**  
   Mitigación: IDs correlacionados (`request_id`, `document_id`, `chunk_id`) obligatorios.

5. **Bloqueos por formatos complejos**  
   Mitigación: cola de fallback OCR + soporte gradual por tipo MIME.

---

## 19) Definición de terminado (Definition of Done)

Un incremento se considera terminado cuando:

- Tiene tests verdes (unit + integración del flujo tocado).
- Tiene métricas instrumentadas y visibles.
- Tiene manejo de errores y reintentos controlados.
- Tiene documentación mínima de operación.
- Tiene validación de seguridad por colección.
- Tiene rollback o estrategia de reversión definida.
