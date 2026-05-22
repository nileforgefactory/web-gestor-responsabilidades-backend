# Plan de Desarrollo — Gestor de Responsabilidades
**Versión:** 1.0  
**Fecha:** 2026-05-10  
**Autor:** Darwin Fierro  
**Estado:** Borrador aprobado

---

## Visión del Producto

Sistema inteligente de análisis de planes de desarrollo territorial colombiano que, mediante agentes de IA orquestados, extrae responsabilidades, leyes y actores de documentos oficiales, los compara contra el RAG de normativa vigente (respetando la jerarquía jurídica colombiana) y genera una **Matriz de Responsabilidades** con brechas de cumplimiento clasificadas por nivel territorial (nacional, departamental, municipal) y sector.

---

## Principios de Diseño

1. **Jerarquía jurídica colombiana siempre presente** — Constitución > Ley > Decreto > Ordenanza > Acuerdo
2. **Trazabilidad total** — cada responsabilidad en la matriz tiene fuente, chunk, score de confianza
3. **Orquestación dinámica** — la IA decide qué buscar y cuándo tiene suficiente contexto
4. **Seguridad por defecto** — autenticación en toda la API, puertos internos cerrados
5. **Streaming real** — el usuario ve el progreso en tiempo real con reconexión automática
6. **Normalización de datos** — catálogos de sectores, actores y normas para evitar duplicados

---

## Stack Tecnológico

### Backend
| Capa | Tecnología | Justificación |
|---|---|---|
| Framework | FastAPI (Python 3.12) | Async nativo, SSE, OpenAPI |
| Vector DB | Qdrant | Filtros por metadata, cosine similarity |
| LLM local | Ollama (llama3.1:8b) | Mejor calidad que 3b para análisis legal |
| Embeddings | nomic-embed-text (768d) | Modelo validado |
| Relacional | MySQL 8.0 | Persistencia estructurada |
| Cache/sesiones | Redis 7 | SSE reconnect, rate limiting, sesiones |
| Auth | JWT + API Keys | Roles por nivel territorial |
| OCR | pytesseract + pdf2image | Extracción de PDFs escaneados |
| Contenedores | Docker Compose | Dev environment reproducible |

### Frontend
| Capa | Tecnología | Justificación |
|---|---|---|
| Framework | Angular 20 (standalone) | Ya implementado, mantener |
| Estado | Angular Signals + computed | Reactivo, sin NgRx |
| Estilos | CSS Variables + design tokens | Ya implementado |
| SSE | EventSource nativo + polyfill | Reconexión automática |
| Gráficos | Chart.js o D3.js lite | Visualización de cobertura |
| Auth | JWT en localStorage | Simple para MVP |

---

## Fases del Proyecto

```
FASE 0 — Fundamentos Críticos      [Semanas 1–2]   ← sin esto no se puede continuar
FASE 1 — RAG Mejorado              [Semanas 3–5]   ← calidad del análisis
FASE 2 — Orquestación Avanzada     [Semanas 6–9]   ← loop agentico + trazabilidad
FASE 3 — Frontend Completo         [Semanas 10–14] ← paridad con prototipo
FASE 4 — Escalabilidad y Roles     [Semanas 15–18] ← multi-tenant, worker remoto
```

---

# FASE 0 — Fundamentos Críticos
**Duración:** 2 semanas  
**Objetivo:** Estabilizar el sistema existente. Sin estos cambios, las fases posteriores construyen sobre bases inseguras.

---

## Sprint 0.1 — Seguridad (Semana 1, días 1–3)

### Tarea 0.1.1 — Cerrar puertos internos en Docker
**Archivos:** `docker-compose.yml`

Problema actual: MySQL (3307), Qdrant (6333), Ollama (11434) expuestos al host.

```yaml
# ANTES (inseguro)
services:
  mysql:
    ports:
      - "3307:3306"

# DESPUÉS (seguro)
services:
  mysql:
    expose:
      - "3306"          # solo visible en red interna docker
    # SIN ports: bloque
  qdrant:
    expose:
      - "6333"
      - "6334"
  ollama:
    expose:
      - "11434"
  api:
    ports:
      - "8000:8000"     # único punto de entrada público
```

### Tarea 0.1.2 — Sistema de autenticación con API Keys y JWT

**Archivos nuevos:**
- `app/core/auth.py`
- `app/core/security.py`
- `app/slices/auth/` (router, schemas, models)

**Flujo de autenticación:**
```
POST /api/v1/auth/login
  body: { email, password }
  → { access_token (JWT 8h), refresh_token (JWT 7d), user: { id, nombre, rol, nivel } }

POST /api/v1/auth/refresh
  header: Authorization: Bearer <refresh_token>
  → { access_token }

GET /api/v1/auth/me
  header: Authorization: Bearer <access_token>
  → { id, nombre, email, rol, nivel, entidad }
```

**Roles del sistema:**
```python
class Rol(str, Enum):
    SUPER_ADMIN = "super_admin"      # acceso total
    ADMIN_NACIONAL = "admin_nacional"  # ve todos los planes
    ADMIN_DEPARTAMENTAL = "admin_departamental"  # ve su depto + municipios
    ADMIN_MUNICIPAL = "admin_municipal"  # ve solo su municipio
    ANALISTA = "analista"            # puede analizar, no administrar
    VIEWER = "viewer"                # solo lectura
```

**Implementación `app/core/auth.py`:**
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> UserOut:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    user = await user_repo.get_by_id(db, user_id)
    if not user or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user

def require_rol(*roles: Rol):
    async def checker(user: UserOut = Depends(get_current_user)):
        if user.rol not in roles:
            raise HTTPException(status_code=403, detail="Sin permiso")
        return user
    return checker
```

**Tabla MySQL nueva:**
```sql
CREATE TABLE usuarios (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    nombre      VARCHAR(100) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol         ENUM('super_admin','admin_nacional','admin_departamental',
                     'admin_municipal','analista','viewer') DEFAULT 'viewer',
    nivel       ENUM('nacional','departamental','municipal','sectorial'),
    entidad_id  VARCHAR(100),
    activo      BOOLEAN DEFAULT TRUE,
    ultimo_login TIMESTAMP,
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Sprint 0.2 — Resiliencia de Agentes (Semana 1, días 4–5)

### Tarea 0.2.1 — Retry en chat de Ollama

**Archivo:** `app/slices/rag/ollama_client.py`

```python
import asyncio
from typing import TypeVar, Callable, Awaitable

T = TypeVar("T")

async def with_retries(
    fn: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    label: str = ""
) -> T:
    last_error = None
    for attempt in range(max_retries):
        try:
            return await fn()
        except OllamaError as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
                await asyncio.sleep(delay)
    raise OllamaError(f"[{label}] Falló tras {max_retries} intentos: {last_error}")

# Uso en agentes:
result = await with_retries(
    lambda: ollama_chat(system_prompt, user_prompt),
    max_retries=3,
    label="leyes_agent"
)
```

### Tarea 0.2.2 — Grafo de dependencias entre agentes

**Archivo:** `app/slices/analysis/service.py`

```python
AGENT_DEPENDENCIES = {
    "matriz":  ["responsabilidades", "leyes", "actores"],
    "brechas": ["responsabilidades"],
}

async def run_parallel_agents(agents: list, context: dict) -> dict[str, Any]:
    results = {}
    
    async def run_one(name: str, fn: Callable) -> None:
        try:
            results[name] = await fn()
            await _emit({"type": "agent_done", "agent": name, "count": len(results[name])})
        except Exception as e:
            results[name] = None
            await _emit({"type": "agent_error", "agent": name, "error": str(e)})
    
    await asyncio.gather(*[run_one(name, fn) for name, fn in agents])
    
    # Advertir si agentes con dependencias recibieron contexto incompleto
    for dep_agent, deps in AGENT_DEPENDENCIES.items():
        failed_deps = [d for d in deps if results.get(d) is None]
        if failed_deps:
            await _emit({
                "type": "warning",
                "msg": f"'{dep_agent}' ejecutará con contexto incompleto. "
                       f"Agentes fallidos: {failed_deps}"
            })
    
    return results
```

---

## Sprint 0.3 — Cambio de Modelo LLM (Semana 2, días 1–2)

### Tarea 0.3.1 — Actualizar modelo en configuración

**Archivo:** `app/core/config.py`

```python
class Settings(BaseSettings):
    # ANTES: ollama_chat_model: str = "llama3.2:3b"
    # DESPUÉS:
    ollama_chat_model: str = "llama3.1:8b"
    
    # Modelo según profundidad de análisis
    ollama_chat_model_basico: str = "llama3.2:3b"     # rápido, básico
    ollama_chat_model_estandar: str = "llama3.1:8b"   # balance calidad/tiempo
    ollama_chat_model_profundo: str = "llama3.1:8b"   # máxima calidad
    
    # Nuevos parámetros de análisis
    analysis_max_iterations: int = 5
    analysis_min_chunks_per_agent: int = 3
    analysis_confidence_threshold: float = 0.60
    analysis_chunk_size: int = 700
    analysis_chunk_overlap: int = 120
```

**Actualizar `docker-compose.yml` — pull de llama3.1:8b:**
```yaml
ollama-pull:
  build:
    context: .
    dockerfile: Dockerfile.ollama-init
  command: >
    sh -c "
      ollama pull nomic-embed-text &&
      ollama pull llama3.1:8b &&
      ollama pull llama3.2:3b
    "
```

---

## Sprint 0.4 — Catálogo de Sectores Normalizado (Semana 2, días 3–5)

### Tarea 0.4.1 — Tabla de sectores y normalización

**Archivo:** `database/schema.sql` + modelo ORM

```sql
CREATE TABLE sectores_catalogo (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    codigo   VARCHAR(50) UNIQUE NOT NULL,  -- ej: "salud", "educacion"
    nombre   VARCHAR(100) NOT NULL,         -- ej: "Salud"
    icono    VARCHAR(50),                   -- ej: "🏥"
    descripcion TEXT,
    nivel_aplicacion ENUM('nacional','departamental','municipal','todos') DEFAULT 'todos',
    activo   BOOLEAN DEFAULT TRUE
);

-- Datos iniciales — sectores colombianos estándar
INSERT INTO sectores_catalogo (codigo, nombre, icono, nivel_aplicacion) VALUES
('salud',           'Salud',                    '🏥', 'todos'),
('educacion',       'Educación',                '🎓', 'todos'),
('agua',            'Agua y Saneamiento',       '💧', 'todos'),
('vivienda',        'Vivienda',                 '🏠', 'todos'),
('transporte',      'Transporte e Infraestructura', '🛣️', 'todos'),
('medio_ambiente',  'Medio Ambiente',           '🌿', 'todos'),
('cultura',         'Cultura',                  '🎭', 'todos'),
('deporte',         'Deporte y Recreación',     '⚽', 'todos'),
('seguridad',       'Seguridad y Convivencia',  '🛡️', 'todos'),
('desarrollo_eco',  'Desarrollo Económico',     '📈', 'todos'),
('gobierno',        'Gobierno y Gestión Pública','🏛️', 'todos'),
('tic',             'TIC e Innovación',         '💻', 'todos'),
('inclusion',       'Inclusión Social',         '🤝', 'todos'),
('agro',            'Sector Agropecuario',      '🌾', 'nacional'),
('mineria',         'Minería y Energía',        '⚡', 'nacional');

-- Función de normalización en Python (app/core/normalizer.py)
-- convierte "Salud Pública", "SALUD", "salud" → "salud"
```

**Archivo nuevo `app/core/normalizer.py`:**
```python
import unicodedata, re

SECTOR_ALIASES = {
    "salud publica": "salud",
    "sector salud": "salud",
    "educacion basica": "educacion",
    "agua potable": "agua",
    "saneamiento basico": "agua",
    "vias": "transporte",
    "infraestructura vial": "transporte",
    "medio ambiente y desarrollo sostenible": "medio_ambiente",
}

def normalize_sector(raw: str) -> str:
    clean = unicodedata.normalize("NFKD", raw.lower().strip())
    clean = re.sub(r"[^\w\s]", "", clean).strip()
    return SECTOR_ALIASES.get(clean, clean.replace(" ", "_"))
```

---

## Sprint 0.5 — Versionado de Análisis (Semana 2, días 3–5)

### Tarea 0.5.1 — Historial de análisis

```sql
CREATE TABLE analisis_historial (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    plan_id             INT NOT NULL,
    version             INT NOT NULL DEFAULT 1,
    profundidad         ENUM('basico','estandar','profundo'),
    modelo_usado        VARCHAR(100),
    duracion_segundos   FLOAT,
    resp_extraidas      INT DEFAULT 0,
    leyes_extraidas     INT DEFAULT 0,
    brechas_encontradas INT DEFAULT 0,
    confianza_promedio  FLOAT,
    creado_por          INT,                    -- FK usuarios
    snapshot_json       LONGTEXT,               -- JSON completo del análisis
    creado_en           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE CASCADE,
    FOREIGN KEY (creado_por) REFERENCES usuarios(id)
);
```

```python
# Al crear un análisis, auto-incrementar versión:
async def create_analysis_version(db, plan_id: int, result: dict, meta: dict) -> int:
    last = await db.execute(
        select(func.max(AnalisisHistorial.version))
        .where(AnalisisHistorial.plan_id == plan_id)
    )
    next_version = (last.scalar() or 0) + 1
    record = AnalisisHistorial(
        plan_id=plan_id,
        version=next_version,
        snapshot_json=json.dumps(result, ensure_ascii=False),
        **meta
    )
    db.add(record)
    await db.commit()
    return next_version
```

---

# FASE 1 — RAG Mejorado
**Duración:** 3 semanas (semanas 3–5)  
**Objetivo:** Mejorar dramáticamente la calidad del contexto que reciben los agentes.

---

## Sprint 1.1 — Jerarquía Jurídica en Prompts (Semana 3)

### Tarea 1.1.1 — Sistema de prompts dinámicos

**Archivo nuevo:** `app/core/prompt_builder.py`

```python
from pathlib import Path
import re

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "data" / "prompts"

JERARQUIA_JURIDICA_COLOMBIANA = """
## Jerarquía Jurídica Colombiana (orden de supremacía)

1. **Constitución Política de Colombia (1991)** — norma de normas
2. **Leyes Orgánicas** (Ley Orgánica de Ordenamiento Territorial, Ley 617/2000)
3. **Leyes Estatutarias** (derechos fundamentales)
4. **Leyes Ordinarias** — Ley 715/2001 (SGP), Ley 136/1994 (municipios), 
   Ley 1454/2011 (LOOT), Ley 152/1994 (planes de desarrollo)
5. **Decretos Ley / Decretos con fuerza de ley**
6. **Decretos Reglamentarios** (del Presidente de la República)
7. **Resoluciones Ministeriales**
8. **Ordenanzas Departamentales** (Asamblea Departamental)
9. **Acuerdos Municipales** (Concejo Municipal)
10. **Decretos Alcaldes / Gobernadores**
11. **Circulares Administrativas**

**Regla cardinal:** Una norma inferior NO puede contradecir una superior.
Al detectar conflicto entre normas, prevalece la de mayor jerarquía.
Al reportar una brecha, indicar qué nivel jerárquico la obliga.
"""

CONTEXTO_POR_NIVEL = {
    "municipal": """
## Marco Normativo Municipal Prioritario
- **Ley 136/1994** — Organización y funcionamiento de municipios
- **Ley 715/2001** — Sistema General de Participaciones (competencias y recursos)
- **Ley 1551/2012** — Modernización del funcionamiento municipal
- **Ley 152/1994** — Ley Orgánica del Plan de Desarrollo
- **Ley 617/2000** — Racionalización del gasto y sostenibilidad fiscal
- **Ley 1454/2011** — LOOT (Ley Orgánica de Ordenamiento Territorial)
El municipio tiene competencias **propias**, **concurrentes** (con depto/nación) 
y **delegadas** (por acuerdo con otros niveles).
""",
    "departamental": """
## Marco Normativo Departamental Prioritario
- **Ley 617/2000** — Racionalización del gasto público departamental
- **Ley 715/2001** — SGP competencias departamentales
- **Ley 1454/2011** — LOOT ordenamiento territorial
- **Ley 1530/2012** — Sistema General de Regalías
- **Decreto 1222/1986** — Régimen departamental
El departamento coordina, complementa y concurre con municipios y nación.
""",
    "nacional": """
## Marco Normativo Nacional
- **Constitución Política arts. 113–211** — estructura del Estado
- **Ley 489/1998** — Organización de la administración pública
- **Ley 152/1994** — Plan Nacional de Desarrollo
- **Ley 715/2001** — Distribución de competencias SGP
El nivel nacional fija política, estándares mínimos y distribución de recursos.
""",
}

PROFUNDIDAD_INSTRUCCIONES = {
    "basico": """
## Nivel de Análisis: BÁSICO
- Extrae las responsabilidades principales (máximo 10)
- Identifica las 5 leyes más relevantes
- No analices brechas complejas
""",
    "estandar": """
## Nivel de Análisis: ESTÁNDAR
- Extrae TODAS las responsabilidades mencionadas
- Identifica todas las leyes, decretos y resoluciones citadas
- Identifica actores institucionales
- Señala brechas evidentes (responsabilidades sin actor o sin ley base)
""",
    "profundo": """
## Nivel de Análisis: PROFUNDO
- Extrae TODAS las responsabilidades, incluyendo las implícitas
- Correlaciona con la normativa vigente del RAG
- Identifica TODAS las brechas incluyendo:
  * Responsabilidades sin actor asignado (brecha crítica)
  * Responsabilidades duplicadas entre actores (duplicidad)
  * Normas vigentes que aplican pero NO están mencionadas en el plan (omisión)
  * Conflictos entre normas de diferente jerarquía
  * Responsabilidades a medias (mencionadas pero sin presupuesto o indicador)
- Clasifica severidad: alta / media / baja
""",
}

def build_agent_prompt(
    agent_type: str,
    nivel: str,
    profundidad: str,
    entidad: str = ""
) -> str:
    sections = [
        JERARQUIA_JURIDICA_COLOMBIANA,
        CONTEXTO_POR_NIVEL.get(nivel, ""),
        PROFUNDIDAD_INSTRUCCIONES.get(profundidad, PROFUNDIDAD_INSTRUCCIONES["estandar"]),
    ]
    
    # Cargar template específico del agente desde archivo
    template_path = TEMPLATES_DIR / f"{agent_type}.md"
    if template_path.exists():
        sections.append(template_path.read_text(encoding="utf-8"))
    
    if entidad:
        sections.append(f"\n## Entidad bajo análisis\n{entidad}\n")
    
    return "\n\n---\n\n".join(filter(None, sections))
```

### Tarea 1.1.2 — Templates de agentes en archivos Markdown

**Archivos nuevos en `data/prompts/`:**

`data/prompts/responsabilidades.md`:
```markdown
## Agente: Extractor de Responsabilidades

Eres un analista técnico especializado en normativa territorial colombiana.

Tu tarea es identificar TODAS las responsabilidades, competencias y obligaciones 
que aparecen en el plan de desarrollo analizado.

Para cada responsabilidad, indica:
- **título**: nombre corto de la responsabilidad
- **descripción**: qué implica concretamente
- **tipo**: P (principal/exclusiva) | C (concurrente) | S (subsidiaria) | N (no aplica)
- **sector**: sector al que pertenece (usar códigos del catálogo)
- **referencia_legal**: qué norma la obliga (ej: "Ley 715/2001 art. 43")
- **nivel_obligatoriedad**: obligatoria | recomendada | opcional

Formato de respuesta — lista de items, uno por línea:
- [TITULO] | [DESCRIPCION] | [TIPO] | [SECTOR] | [REF_LEGAL] | [OBLIGATORIEDAD]

Responde SOLO en español. No incluyas explicaciones fuera del formato.
```

`data/prompts/leyes.md`:
```markdown
## Agente: Extractor de Marco Normativo

Eres un experto en normativa territorial colombiana.

Identifica TODAS las leyes, decretos, resoluciones, ordenanzas y acuerdos 
mencionados o que aplican al plan de desarrollo analizado.

Para cada norma:
- **código**: identificador exacto (ej: "Ley 715 de 2001", "Decreto 1075 de 2015")
- **título**: nombre oficial
- **tipo**: ley | decreto_ley | decreto | resolucion | ordenanza | acuerdo | circular
- **artículos**: artículos relevantes (ej: "arts. 43, 44, 76")
- **relevancia**: por qué aplica al plan
- **vigente**: sí | no | parcialmente
- **jerarquía**: número del nivel (1=Constitución, 11=Circular)

Formato:
[CODIGO] | [TITULO] | [TIPO] | [ARTICULOS] | [RELEVANCIA] | [VIGENTE] | [JERARQUIA]
```

`data/prompts/actores.md`:
```markdown
## Agente: Identificador de Actores Institucionales

Identifica TODAS las entidades, instituciones y actores con responsabilidades 
en el plan analizado, respetando los niveles del Estado colombiano:

Niveles: Nacional (Ministerios, DANE, DNP) | Departamental (Gobernación, 
Secretarías Dptal) | Municipal (Alcaldía, Secretarías Mpal, ESP) | 
Especializadas (ICBF, SENA, hospitales, etc.)

Para cada actor:
- **nombre**: nombre oficial completo
- **sigla**: sigla si existe (ej: ICBF)
- **tipo**: principal | concurrente | subsidiario | apoyo
- **nivel**: nacional | departamental | municipal | especializado
- **competencias_clave**: qué hace en el plan

Formato:
[NOMBRE] | [SIGLA] | [TIPO] | [NIVEL] | [COMPETENCIAS]
```

`data/prompts/brechas.md`:
```markdown
## Agente: Auditor de Brechas de Competencias

Eres un auditor crítico de competencias territoriales colombianas.

Analiza el plan e identifica TODAS las brechas, déficits y problemas:

Tipos de brecha:
- **critica**: responsabilidad sin actor asignado O norma violada
- **duplicidad**: dos actores reclaman la misma competencia
- **sin_responsable**: sector sin ningún actor con responsabilidad asignada
- **omision_normativa**: ley vigente que aplica pero no está en el plan
- **alerta**: responsabilidad mencionada pero sin indicador o presupuesto

Para cada brecha:
- **titulo**: nombre corto
- **descripción**: qué falta o está mal
- **tipo**: critica | duplicidad | sin_responsable | omision_normativa | alerta
- **severidad**: alta (incumplimiento legal) | media (riesgo) | baja (mejora)
- **norma_base**: qué norma obliga a resolverla
- **recomendacion**: cómo resolverla

Formato:
[TITULO] | [DESCRIPCION] | [TIPO] | [SEVERIDAD] | [NORMA_BASE] | [RECOMENDACION]
```

`data/prompts/matriz.md`:
```markdown
## Agente: Constructor de Matriz de Competencias

Consolida toda la información de los agentes anteriores en una matriz de 
competencias territoriales colombiana.

La matriz debe tener una fila por competencia/responsabilidad y columnas por 
nivel territorial.

Valores por celda:
- **P**: Principal — responsabilidad exclusiva del nivel
- **C**: Concurrente — comparte con otro nivel
- **S**: Subsidiaria — interviene solo si el principal no puede
- **N**: No aplica — este nivel no tiene responsabilidad

Para cada fila incluye:
- competencia: nombre de la responsabilidad
- ley_base: norma que la asigna
- nacion: P|C|S|N
- departamento: P|C|S|N
- municipio: P|C|S|N
- especializado: P|C|S|N (ICBF, SENA, etc.)
- sector: código de sector
- brecha: ok | critica | duplicidad | alerta | sin_responsable

Responde ÚNICAMENTE con un array JSON válido. Sin texto adicional.
Formato exacto:
[
  {
    "competencia": "...",
    "ley_base": "...",
    "nacion": "P|C|S|N",
    "departamento": "P|C|S|N",
    "municipio": "P|C|S|N",
    "especializado": "P|C|S|N",
    "sector": "...",
    "brecha": "ok|critica|duplicidad|alerta|sin_responsable"
  }
]
```

---

## Sprint 1.2 — Multi-Query RAG con Re-ranking (Semana 4)

### Tarea 1.2.1 — Multi-query search con deduplicación

**Archivo:** `app/slices/rag/service.py` — nuevo método

```python
async def search_multi_query(
    self,
    queries: list[str],
    collection_ids: list[str],
    top_k_per_query: int = 5,
    score_threshold: float = 0.25,
    max_total: int = 12
) -> list[dict]:
    """
    Ejecuta múltiples queries en paralelo, deduplica por chunk_id,
    y re-rankea combinando score de similitud + frecuencia de aparición.
    """
    chunk_results = await asyncio.gather(*[
        self.repo.search_chunks(
            query_vec=await self._embed(q),
            collection_ids=collection_ids,
            top_k=top_k_per_query,
            score_threshold=score_threshold
        )
        for q in queries
    ])
    
    # Deduplicar y calcular score combinado
    seen: dict[str, dict] = {}
    for query_idx, chunks in enumerate(chunk_results):
        for chunk in chunks:
            cid = chunk["payload"]["chunk_id"]
            if cid not in seen:
                seen[cid] = {"chunk": chunk, "hits": 0, "total_score": 0.0}
            seen[cid]["hits"] += 1
            seen[cid]["total_score"] += chunk["score"]
    
    # Re-rankear: score_promedio * (1 + 0.2 * hits)
    ranked = sorted(
        seen.values(),
        key=lambda x: (x["total_score"] / x["hits"]) * (1 + 0.2 * x["hits"]),
        reverse=True
    )
    
    return [r["chunk"] for r in ranked[:max_total]]
```

### Tarea 1.2.2 — Queries especializadas por agente

**Archivo:** `app/slices/analysis/agents.py`

```python
AGENT_QUERIES = {
    "responsabilidades": [
        "responsabilidades y competencias del municipio",
        "obligaciones de la alcaldía y secretarías",
        "funciones asignadas por nivel territorial",
        "metas y compromisos del plan de desarrollo",
    ],
    "leyes": [
        "leyes decretos resoluciones marco normativo",
        "Ley 715 competencias sector salud educación agua",
        "Constitución Política artículos organización territorial",
        "normativa vigente plan de desarrollo territorial",
    ],
    "actores": [
        "entidades instituciones actores responsables",
        "alcaldía gobernación ministerios secretarías",
        "organismos de control y seguimiento",
        "participación institucional plan de desarrollo",
    ],
    "brechas": [
        "responsabilidades sin asignar vacíos normativos",
        "conflicto competencias duplicidad responsabilidades",
        "incumplimiento normativo obligaciones pendientes",
        "sectores sin cobertura institucional",
    ],
}
```

### Tarea 1.2.3 — Peso jurídico en el score de chunks

**Archivo:** `app/slices/rag/service.py`

```python
JERARQUIA_PESOS = {
    "constitucion": 2.0,
    "ley_organica": 1.8,
    "ley_estatutaria": 1.7,
    "ley": 1.5,
    "decreto_ley": 1.4,
    "decreto": 1.2,
    "resolucion": 1.0,
    "ordenanza": 1.1,
    "acuerdo": 1.05,
    "circular": 0.8,
}

def apply_juridical_weight(chunk: dict) -> dict:
    tipo = chunk.get("payload", {}).get("tipo_norma", "")
    peso = JERARQUIA_PESOS.get(tipo, 1.0)
    chunk["adjusted_score"] = chunk["score"] * peso
    return chunk
```

**Al indexar documentos legales, agregar metadata:**
```python
# extract.py — detectar tipo de norma por nombre de archivo
def detect_tipo_norma(filename: str) -> str:
    fname = filename.lower()
    if "constitucion" in fname: return "constitucion"
    if re.match(r"ley[-_]\d+", fname): return "ley"
    if re.match(r"decreto[-_]\d+", fname): return "decreto"
    if "resolucion" in fname: return "resolucion"
    if "ordenanza" in fname: return "ordenanza"
    if "acuerdo" in fname: return "acuerdo"
    return "otro"
```

---

## Sprint 1.3 — Trazabilidad Chunk→Resultado (Semana 5)

### Tarea 1.3.1 — Agregar chunk_ids y confidence_score a todos los resultados

**Modelos actualizados:**
```python
# planes/schemas.py — agregar campos de trazabilidad
class ResponsabilidadCreate(BaseModel):
    titulo: str
    descripcion: str
    sector: str
    tipo: str
    referencia_legal: str | None = None
    icono: str | None = None
    # Nuevos campos de trazabilidad
    chunk_ids: list[str] = []
    confidence_score: float = 1.0
    modelo_usado: str | None = None

class BrechaCreate(BaseModel):
    titulo: str
    descripcion: str
    tipo: str
    severidad: str
    referencia_legal: str | None = None
    # Nuevos
    chunk_ids: list[str] = []
    confidence_score: float = 1.0
    recomendacion: str | None = None
```

**Columnas nuevas en MySQL:**
```sql
ALTER TABLE responsabilidades
    ADD COLUMN chunk_ids      JSON,
    ADD COLUMN confidence_score FLOAT DEFAULT 1.0,
    ADD COLUMN modelo_usado   VARCHAR(100);

ALTER TABLE brechas
    ADD COLUMN chunk_ids      JSON,
    ADD COLUMN confidence_score FLOAT DEFAULT 1.0,
    ADD COLUMN recomendacion  TEXT;
```

### Tarea 1.3.2 — Endpoint de evidencia por responsabilidad

```python
# planes/router.py
@router.get("/{plan_id}/responsabilidades/{resp_id}/evidencia")
async def get_evidencia(
    plan_id: int,
    resp_id: int,
    rag_service: RagService = Depends(get_rag_service),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve los chunks del RAG que originaron esta responsabilidad."""
    resp = await repo.get_responsabilidad(db, resp_id)
    if not resp.chunk_ids:
        return {"chunks": []}
    
    chunks = await rag_service.repo.get_chunks_by_ids(resp.chunk_ids)
    return {"chunks": chunks, "confidence_score": resp.confidence_score}
```

---

# FASE 2 — Orquestación Avanzada
**Duración:** 4 semanas (semanas 6–9)  
**Objetivo:** Implementar el loop agentico iterativo y sesiones de análisis con reconexión.

---

## Sprint 2.1 — Sesiones de Análisis con Redis (Semana 6)

### Tarea 2.1.1 — Redis como broker de sesiones SSE

**Archivo nuevo:** `app/core/session_store.py`

```python
import redis.asyncio as aioredis
import json
from uuid import uuid4

class SessionStore:
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)
        self.TTL = 3600  # 1 hora
    
    async def create_session(self, plan_id: int, user_id: int) -> str:
        session_id = str(uuid4())
        await self.redis.setex(
            f"analysis:{session_id}",
            self.TTL,
            json.dumps({
                "plan_id": plan_id,
                "user_id": user_id,
                "status": "running",
                "events": []
            })
        )
        return session_id
    
    async def append_event(self, session_id: str, event: dict) -> None:
        key = f"analysis:{session_id}"
        data = json.loads(await self.redis.get(key) or "{}")
        data.setdefault("events", []).append(event)
        await self.redis.setex(key, self.TTL, json.dumps(data))
    
    async def get_session(self, session_id: str) -> dict | None:
        raw = await self.redis.get(f"analysis:{session_id}")
        return json.loads(raw) if raw else None
    
    async def mark_done(self, session_id: str) -> None:
        key = f"analysis:{session_id}"
        data = json.loads(await self.redis.get(key) or "{}")
        data["status"] = "done"
        await self.redis.setex(key, self.TTL, json.dumps(data))
```

### Tarea 2.1.2 — Endpoint de replay de sesión

```python
# analysis/router.py
@router.get("/session/{session_id}/replay")
async def replay_session(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
    current_user = Depends(get_current_user)
):
    """
    Permite reconectar a un análisis en curso o ver eventos pasados.
    Devuelve SSE: primero todos los eventos históricos, luego los nuevos.
    """
    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada")
    
    async def generate():
        # Replay de eventos pasados
        for event in session.get("events", []):
            yield f"data: {json.dumps(event)}\n\n"
        
        if session["status"] == "done":
            return
        
        # Suscribirse a nuevos eventos vía Redis Pub/Sub
        pubsub = store.redis.pubsub()
        await pubsub.subscribe(f"analysis_channel:{session_id}")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data'].decode()}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Tarea 2.1.3 — Heartbeat en el stream

```python
# analysis/service.py — agregar heartbeat al generador SSE
async def _stream_with_heartbeat(queue: asyncio.Queue):
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=20.0)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") in ("done", "error"):
                break
        except asyncio.TimeoutError:
            yield 'data: {"type":"heartbeat"}\n\n'
```

---

## Sprint 2.2 — Loop Agentico Iterativo (Semanas 7–8)

### Tarea 2.2.1 — Agente Coordinador

**Archivo nuevo:** `app/slices/analysis/coordinator.py`

```python
"""
El coordinador decide dinámicamente si el análisis tiene suficiente contexto
o si necesita iterar más para cubrir sectores o brechas sin datos.
"""

COORDINATOR_PROMPT = """
Eres el coordinador de un sistema de análisis de planes de desarrollo colombianos.

Has recibido los resultados preliminares de los agentes especializados.
Evalúa si el análisis es suficiente o si necesitas más información.

Resultados actuales:
{resumen_resultados}

Contexto del plan:
- Nivel: {nivel}
- Sectores declarados: {sectores}
- Profundidad solicitada: {profundidad}
- Iteración actual: {iteracion} de {max_iteraciones}

Decide una acción:
1. **finalizar** — el análisis es suficiente
2. **buscar_mas** — necesito más contexto, indica query específica
3. **reanalizar_sector** — un sector tiene cobertura insuficiente, indica cuál

Responde SOLO con JSON:
{
  "accion": "finalizar|buscar_mas|reanalizar_sector",
  "razon": "explicación breve",
  "query": "query para buscar (si accion=buscar_mas)",
  "sector": "sector a reanalizar (si accion=reanalizar_sector)",
  "confianza": 0.0-1.0
}
"""

async def coordinator_decide(
    context: dict,
    nivel: str,
    sectores: list[str],
    profundidad: str,
    iteration: int,
    max_iterations: int
) -> dict:
    resumen = _build_resumen(context)
    
    prompt = COORDINATOR_PROMPT.format(
        resumen_resultados=resumen,
        nivel=nivel,
        sectores=", ".join(sectores),
        profundidad=profundidad,
        iteracion=iteration,
        max_iteraciones=max_iterations
    )
    
    response = await with_retries(
        lambda: ollama_chat(
            system="Eres un coordinador de análisis que responde solo con JSON.",
            user=prompt
        ),
        label="coordinator"
    )
    
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"accion": "finalizar", "razon": "respuesta inválida del coordinador", "confianza": 0.5}

def _build_resumen(context: dict) -> str:
    lines = []
    for agent, results in context.items():
        if results:
            lines.append(f"- {agent}: {len(results)} elementos extraídos")
        else:
            lines.append(f"- {agent}: SIN RESULTADOS (posible fallo)")
    
    # Detectar sectores sin cobertura
    sectores_con_resp = set(r.get("sector") for r in context.get("responsabilidades", []))
    return "\n".join(lines) + f"\nSectores cubiertos: {sectores_con_resp}"
```

### Tarea 2.2.2 — Loop principal de análisis

**Archivo:** `app/slices/analysis/service.py` — refactor del método principal

```python
async def analyze_plan_stream(request: AnalyzePlanRequest, db: AsyncSession):
    queue = asyncio.Queue()
    session_id = await session_store.create_session(request.plan_id, request.user_id)
    
    async def _emit(event: dict):
        await queue.put(event)
        await session_store.append_event(session_id, event)
    
    async def pipeline():
        try:
            context = {
                "responsabilidades": [],
                "leyes": [],
                "actores": [],
                "brechas": [],
                "extra_chunks": [],
            }
            
            # ── ITERACIÓN 0: Análisis inicial ──────────────────────────
            await _emit({"type": "log", "msg": "Iniciando análisis inicial..."})
            
            initial_agents = [
                ("responsabilidades", responsabilidades_agent),
                ("leyes", leyes_agent),
                ("actores", actores_agent),
            ]
            if request.depth == "profundo":
                initial_agents.append(("brechas", brechas_agent))
            
            initial_results = await run_parallel_agents(initial_agents, _emit)
            context.update(initial_results)
            
            # ── LOOP AGENTICO ──────────────────────────────────────────
            max_iter = settings.analysis_max_iterations
            
            for iteration in range(1, max_iter + 1):
                if request.depth == "basico":
                    break  # modo básico: sin loop
                
                await _emit({"type": "log", "msg": f"Evaluando completitud (iteración {iteration}/{max_iter})..."})
                
                decision = await coordinator_decide(
                    context=context,
                    nivel=request.nivel,
                    sectores=request.sectores,
                    profundidad=request.depth,
                    iteration=iteration,
                    max_iterations=max_iter,
                )
                
                await _emit({
                    "type": "coordinator_decision",
                    "accion": decision["accion"],
                    "razon": decision["razon"],
                    "confianza": decision.get("confianza", 1.0),
                })
                
                if decision["accion"] == "finalizar":
                    await _emit({"type": "log", "msg": f"Análisis completo con confianza {decision.get('confianza', 1.0):.0%}"})
                    break
                
                elif decision["accion"] == "buscar_mas":
                    query = decision.get("query", "")
                    new_chunks = await rag_service.search_multi_query(
                        queries=[query],
                        collection_ids=[request.collection_id],
                        top_k_per_query=5,
                    )
                    context["extra_chunks"].extend(new_chunks)
                    
                    # Re-correr agentes con contexto adicional
                    await _emit({"type": "log", "msg": f"Buscando contexto adicional: '{query}'"})
                    new_results = await run_parallel_agents(initial_agents, _emit, extra_chunks=new_chunks)
                    
                    # Merge (evitar duplicados por titulo)
                    for agent_name, new_items in new_results.items():
                        existing = {r.get("titulo") for r in context.get(agent_name, [])}
                        context[agent_name] += [r for r in (new_items or []) if r.get("titulo") not in existing]
                
                elif decision["accion"] == "reanalizar_sector":
                    sector = decision.get("sector", "")
                    await _emit({"type": "log", "msg": f"Profundizando en sector: {sector}"})
                    
                    sector_chunks = await rag_service.search_multi_query(
                        queries=[
                            f"responsabilidades {sector} municipal",
                            f"ley norma {sector} colombia",
                        ],
                        collection_ids=[request.collection_id],
                    )
                    sector_resp = await responsabilidades_agent(
                        rag_service, request.collection_id, request.depth,
                        extra_chunks=sector_chunks, sector_filter=sector
                    )
                    context["responsabilidades"] += sector_resp or []
            
            # ── CONSOLIDACIÓN: Matriz ──────────────────────────────────
            if request.depth in ("estandar", "profundo"):
                await _emit({"type": "agent_start", "agent": "matriz"})
                matriz = await with_retries(
                    lambda: matriz_agent(rag_service, request.collection_id, context),
                    label="matriz"
                )
                context["matriz"] = matriz
                await _emit({"type": "agent_done", "agent": "matriz", "count": len(matriz or [])})
            
            # ── PERSISTENCIA ───────────────────────────────────────────
            await _emit({"type": "saving", "msg": "Guardando resultados en base de datos..."})
            plan_id = await _persist_results(db, request, context)
            
            await session_store.mark_done(session_id)
            await _emit({"type": "done", "plan_id": plan_id, "session_id": session_id})
        
        except Exception as e:
            await _emit({"type": "error", "error": str(e), "session_id": session_id})
    
    asyncio.create_task(pipeline())
    return _stream_with_heartbeat(queue), session_id
```

---

## Sprint 2.3 — Alertas Normativas Automáticas (Semana 9)

### Tarea 2.3.1 — Sistema de alertas por cambios normativos

**Tabla nueva:**
```sql
CREATE TABLE alertas_normativas (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    plan_id     INT,
    norma_id    INT,
    tipo        ENUM('modificacion','derogacion','nueva_norma','jurisprudencia'),
    titulo      VARCHAR(200),
    descripcion TEXT,
    severidad   ENUM('alta','media','baja') DEFAULT 'media',
    leida       BOOLEAN DEFAULT FALSE,
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plan_id) REFERENCES planes(id),
    FOREIGN KEY (norma_id) REFERENCES plan_normas(id)
);
```

**Servicio de alertas:**
```python
# app/slices/alertas/service.py
async def check_normas_actualizadas(db: AsyncSession, plan_id: int) -> list[AlertaNormativa]:
    """
    Compara las normas del plan contra el RAG para detectar
    normas que han sido modificadas o derogadas.
    """
    normas = await repo.get_normas_plan(db, plan_id)
    alertas = []
    
    for norma in normas:
        # Buscar en RAG si hay versión más reciente
        chunks = await rag_service.search_chunks(
            query=f"{norma.norma_codigo} modificación derogación actualización",
            collection_ids=["normas_legales"],
            top_k=3,
        )
        
        for chunk in chunks:
            texto = chunk["payload"]["text"].lower()
            if any(kw in texto for kw in ["derogado", "modificado", "sustituido"]):
                alertas.append(AlertaNormativa(
                    plan_id=plan_id,
                    norma_id=norma.id,
                    tipo="modificacion",
                    titulo=f"{norma.norma_codigo} puede haber sido modificada",
                    descripcion=chunk["payload"]["text"][:500],
                    severidad="alta" if norma.relevancia == "alta" else "media",
                ))
    
    return alertas

# Endpoint:
# GET /api/v1/planes/{plan_id}/alertas
```

---

# FASE 3 — Frontend Completo
**Duración:** 5 semanas (semanas 10–14)  
**Objetivo:** Paridad con el prototipo HTML. Login, dashboards, matriz interactiva, alertas.

---

## Sprint 3.1 — Autenticación en Angular (Semana 10)

### Tarea 3.1.1 — Auth service con JWT

**Archivo nuevo:** `src/app/core/services/auth.service.ts`
```typescript
@Injectable({ providedIn: 'root' })
export class AuthService {
  private _user = signal<UserProfile | null>(null);
  readonly user = this._user.asReadonly();
  readonly isLoggedIn = computed(() => !!this._user());
  readonly rol = computed(() => this._user()?.rol);

  async login(email: string, password: string): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<LoginResponse>('/api/v1/auth/login', { email, password })
    );
    localStorage.setItem('access_token', res.access_token);
    localStorage.setItem('refresh_token', res.refresh_token);
    this._user.set(res.user);
  }

  async loadCurrentUser(): Promise<void> {
    const token = localStorage.getItem('access_token');
    if (!token) return;
    try {
      const user = await firstValueFrom(this.http.get<UserProfile>('/api/v1/auth/me'));
      this._user.set(user);
    } catch { this.logout(); }
  }

  logout(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    this._user.set(null);
  }
}
```

**Auth Guard:**
```typescript
// core/guards/auth.guard.ts
export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isLoggedIn()) return true;
  return router.createUrlTree(['/login']);
};

// Rutas actualizadas:
{ path: 'login', component: LoginComponent },
{ path: '', canActivate: [authGuard], children: [
    { path: 'cargar-plan', component: CargarPlanComponent },
    { path: 'biblioteca', component: BibliotecaPlanes },
    // ...
]}
```

### Tarea 3.1.2 — Pantalla de Login con selector de rol

```typescript
// features/login/login.component.ts
// Diseño: card centrada, email+pass, selector de nivel territorial
// Al hacer login → redirigir según rol:
// admin_nacional → /dashboard-nacional
// admin_departamental / admin_municipal → /dashboard
// analista → /cargar-plan
```

---

## Sprint 3.2 — Dashboard por Nivel (Semana 11)

### Tarea 3.2.1 — Dashboard Municipal (principal)

**Componentes nuevos:**
- `features/dashboard/dashboard.component.ts`
- `features/dashboard/components/stats-bar/`  — 4 KPIs (resp, leyes, brechas, avance)
- `features/dashboard/components/matriz-preview/` — mini-matriz top 5 competencias
- `features/dashboard/components/alertas-panel/` — alertas normativas recientes
- `features/dashboard/components/planes-recientes/` — tabla últimos 5 planes

**Stats del dashboard:**
```typescript
interface DashboardStats {
  totalResponsabilidades: number;
  totalConcurrentes: number;
  totalLeyes: number;
  avancePct: number;
  brechasCriticas: number;
  alertasActivas: number;
  planesAnalizados: number;
}
```

### Tarea 3.2.2 — Dashboard Nacional

- Tabla de planes activos por departamento
- Mapa (SVG) de Colombia con cobertura por color
- Top 5 brechas críticas a nivel nacional
- Estadísticas globales: total municipios, planes, leyes indexadas

---

## Sprint 3.3 — Matriz Interactiva (Semana 12)

### Tarea 3.3.1 — Tabla de matriz con colores y filtros

**Archivo:** `shared/components/result-tabs/result-tabs.component.ts`

```typescript
// Colorización por estado de brecha
getRowClass(row: MatrizRow): string {
  return {
    'ok':              'row-verde',
    'alerta':          'row-gold',
    'critica':         'row-rojo',
    'duplicidad':      'row-naranja',
    'sin_responsable': 'row-gris',
  }[row.brecha] ?? '';
}

// CSS:
// .row-verde { background: #d1fae5; }
// .row-gold  { background: #fef3c7; }
// .row-rojo  { background: #fee2e2; }
```

**Filtros de la matriz:**
```typescript
filtroSector = signal<string>('todos');
filtroNivel  = signal<'nacion'|'departamento'|'municipio'|'todos'>('todos');
filtroBrecha = signal<string>('todos');

matrizFiltrada = computed(() =>
  this.rows().filter(r =>
    (this.filtroSector() === 'todos' || r.sector === this.filtroSector()) &&
    (this.filtroBrecha() === 'todos' || r.brecha === this.filtroBrecha())
  )
);
```

**Estadísticas de la matriz:**
```typescript
stats = computed(() => ({
  sinResponsable: this.rows().filter(r => r.brecha === 'sin_responsable').length,
  duplicidades:   this.rows().filter(r => r.brecha === 'duplicidad').length,
  criticas:       this.rows().filter(r => r.brecha === 'critica').length,
  alertas:        this.rows().filter(r => r.brecha === 'alerta').length,
  ok:             this.rows().filter(r => r.brecha === 'ok').length,
}));
```

### Tarea 3.3.2 — Drill-down de evidencia

Al hacer click en una celda de la matriz → modal con:
- Texto del chunk del RAG que originó esa responsabilidad
- Score de confianza con barra visual
- Ley base con enlace a texto completo
- Botón "Ver en RAG" → navega a BusquedaRAG con query pre-llenada

---

## Sprint 3.4 — Panel de Agentes y Reconexión SSE (Semana 13)

### Tarea 3.4.1 — Panel de estado de agentes

**Feature nuevo:** `features/agentes-panel/`

```typescript
interface AgentStatus {
  name: string;
  label: string;
  icon: string;
  status: 'idle' | 'running' | 'done' | 'error';
  items_found: number;
  duration_ms: number;
  confidence: number;
}

// Agentes mostrados:
// RAG Agent, Responsabilidades, Leyes, Actores, Brechas, Coordinador, Matriz
```

Muestra el flujo de orquestación:
```
Indexación → [Resp | Leyes | Actores] → Coordinador ─┬─ Finalizar
                                                       ├─ Buscar más → loop
                                                       └─ Reanalizar sector → loop
                                         → Matriz → Guardar
```

### Tarea 3.4.2 — Reconexión SSE automática

**Archivo:** `core/services/rag-api.service.ts`

```typescript
analyzePlanStream(request: AnalyzePlanRequest): Observable<AnalysisEvent> {
  return new Observable(subscriber => {
    let sessionId: string | null = null;
    
    const connect = async (lastEventId?: string) => {
      const url = lastEventId
        ? `/api/v1/analysis/session/${lastEventId}/replay`
        : '/api/v1/analysis/analyze-plan/stream';
      
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...this.authHeaders() },
        body: JSON.stringify(request),
      });
      
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        
        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          const event: AnalysisEvent = JSON.parse(line.slice(5).trim());
          
          if (event.type === 'done' && event.session_id) {
            sessionId = event.session_id;
          }
          subscriber.next(event);
          if (event.type === 'done' || event.type === 'error') {
            subscriber.complete();
            return;
          }
        }
      }
    };
    
    connect().catch(err => {
      // Reconexión automática con backoff
      if (sessionId) {
        setTimeout(() => connect(sessionId!), 2000);
      } else {
        subscriber.error(err);
      }
    });
  });
}
```

---

## Sprint 3.5 — Alertas y Búsqueda Mejorada (Semana 14)

### Tarea 3.5.1 — Panel de alertas normativas

**Componente:** `shared/components/alertas-normativas/`

```typescript
// Muestra alertas del endpoint GET /api/v1/planes/{id}/alertas
// Tarjeta por alerta: tipo, título, descripción, severidad, botón "Ver norma"
// Filtro por leída/no leída
// Badge en navbar con conteo de alertas no leídas
```

### Tarea 3.5.2 — Resultados RAG con acciones

**Actualizar:** `features/busqueda-raag/`

```typescript
// Agregar botones a cada resultado:
// [+ Agregar al plan activo] → POST /api/v1/planes/{id}/normas
// [Ver en matriz]           → navega a /plan/{id} tab=matriz con filtro
// [Exportar]                → descarga texto del chunk
// Barra de relevancia con % y color (verde/amarillo/rojo por score)
// Filtro por tipo: ley | decreto | resolucion | ordenanza
// Filtro por jerarquía: constitucional | legal | reglamentario | territorial
```

---

# FASE 4 — Escalabilidad y Roles Avanzados
**Duración:** 4 semanas (semanas 15–18)  
**Objetivo:** Multi-tenant, worker remoto para análisis pesado, exportación de reportes.

---

## Sprint 4.1 — Multi-tenant por Entidad (Semana 15)

### Tarea 4.1.1 — Aislamiento de datos por entidad

```python
# Agregar entidad_id a planes, conocimiento, análisis
# Los queries filtran automáticamente por entidad del usuario autenticado

async def list_planes_for_user(db, user: UserOut) -> list[PlanSummary]:
    query = select(Plane)
    if user.rol not in (Rol.SUPER_ADMIN, Rol.ADMIN_NACIONAL):
        query = query.where(Plane.entidad_id == user.entidad_id)
    return await db.execute(query)
```

### Tarea 4.1.2 — Admin panel en Angular

**Feature nuevo:** `features/admin/`
- CRUD de usuarios (solo super_admin)
- Estadísticas globales (total municipios, planes, leyes, brechas)
- Timeline de análisis recientes
- Estado de salud del sistema (API, Qdrant, Ollama, MySQL, Redis)

---

## Sprint 4.2 — Worker Remoto de Análisis (Semana 16)

### Inspirado en MiniPWN worker mode

**Arquitectura:**
```
FastAPI (coordinador) → HTTP → Analysis Worker (GPU, modelo mayor)
```

**Worker API:**
```python
# worker/main.py — servidor separado para análisis pesado
@app.post("/analyze")
async def analyze(request: AnalyzeRequest, auth: str = Depends(verify_bearer)):
    """Worker especializado con llama3.1:70b o mixtral para análisis críticos."""
    result = await run_agents(request)
    return result

# Configuración en el coordinador:
# Si depth="profundo" y worker_url configurado → delegar al worker
# Si no → análisis local con llama3.1:8b
```

---

## Sprint 4.3 — Exportación de Reportes (Semana 17)

### Tarea 4.3.1 — Generación de reporte PDF/Markdown

```python
# app/slices/reportes/service.py
async def generate_report_markdown(plan_id: int, db: AsyncSession) -> str:
    plan = await repo.get_plane(db, plan_id)
    
    template = f"""
# Informe de Responsabilidades — {plan.titulo}
**Entidad:** {plan.entidad}
**Período:** {plan.periodo}
**Nivel:** {plan.nivel}
**Fecha de análisis:** {datetime.now().strftime('%Y-%m-%d')}

## Resumen Ejecutivo
- Responsabilidades identificadas: {plan.resp_total}
- Marco normativo: {plan.leyes_total} normas
- Actores institucionales: {plan.actores_total}
- Brechas detectadas: {plan.brechas_total}
- Avance de cumplimiento: {plan.avance_pct}%

## Matriz de Responsabilidades
{_render_matriz_md(plan.matriz)}

## Brechas Críticas
{_render_brechas_md(plan.brechas)}

## Marco Normativo Aplicable
{_render_normas_md(plan.normas)}

## Recomendaciones
{_generate_recommendations(plan)}
"""
    return template

# Endpoint: GET /api/v1/planes/{id}/reporte?format=md|pdf
```

---

## Sprint 4.4 — Scraper de Normativa (Semana 18)

### Tarea 4.4.1 — Agente scraper de fuentes oficiales

```python
# app/slices/scraper/service.py
FUENTES_OFICIALES = [
    {
        "nombre": "Secretaría del Senado",
        "url": "http://www.secretariasenado.gov.co",
        "tipo": "ley",
        "selector": "a[href*='ley']"
    },
    {
        "nombre": "Función Pública",
        "url": "https://www.funcionpublica.gov.co",
        "tipo": "decreto",
        "selector": "a[href*='decreto']"
    },
    {
        "nombre": "DNP — Planes de Desarrollo",
        "url": "https://colaboracion.dnp.gov.co",
        "tipo": "plan",
        "selector": "a[href*='pdf']"
    },
]

# Tarea programada: ejecutar cada 24h
# Al encontrar nueva norma → indexar en Qdrant + registrar en base_conocimiento
# Comparar contra normas existentes → crear alertas_normativas si hay cambios
```

---

## Resumen de Entregables por Fase

| Fase | Semanas | Entregables clave |
|---|---|---|
| **0 — Críticos** | 1–2 | Auth JWT+roles, Docker seguro, retry agentes, modelo 8b, catálogo sectores, versionado |
| **1 — RAG** | 3–5 | Prompts con jerarquía jurídica, multi-query, peso jurídico, trazabilidad chunk→resultado |
| **2 — Orquestación** | 6–9 | Sesiones Redis, reconexión SSE, loop agentico con coordinador, alertas normativas |
| **3 — Frontend** | 10–14 | Login+roles, dashboards, matriz interactiva con drill-down, panel agentes, alertas UI |
| **4 — Escala** | 15–18 | Multi-tenant, worker remoto, exportación PDF, scraper normativo |

---

## Estimación de Esfuerzo

| Fase | Dev Backend | Dev Frontend | Total |
|---|---|---|---|
| Fase 0 | 6 días | 2 días | **8 días** |
| Fase 1 | 8 días | 2 días | **10 días** |
| Fase 2 | 10 días | 4 días | **14 días** |
| Fase 3 | 4 días | 14 días | **18 días** |
| Fase 4 | 12 días | 6 días | **18 días** |
| **Total** | **40 días** | **28 días** | **68 días hábiles** |

> Asumiendo 1 desarrollador full-stack: ~14 semanas (~3.5 meses)
> Con 2 desarrolladores (1 back + 1 front): ~9 semanas (~2 meses)

---

## Dependencias Críticas del Proyecto

```
Auth (0.1) ─────────────────────────────────────────────→ Todo lo demás
Retry agentes (0.2) ────────────────────────────────────→ Loop agentico (2.2)
Catálogo sectores (0.4) ────────────────────────────────→ Matriz interactiva (3.3)
Versionado análisis (0.5) ──────────────────────────────→ Admin panel (4.1)
Jerarquía en prompts (1.1) ─────────────────────────────→ Calidad matriz
Multi-query RAG (1.2) ──────────────────────────────────→ Coordinador (2.2)
Redis sesiones (2.1) ───────────────────────────────────→ Reconexión SSE (3.4)
Loop coordinador (2.2) ─────────────────────────────────→ Worker remoto (4.2)
```

---

## Stack Final de Infraestructura

```yaml
# docker-compose.yml final
services:
  api:          FastAPI 8000 (público)
  worker:       Analysis Worker 8001 (interno, GPU opcional)
  mysql:        MySQL 8.0 (interno)
  redis:        Redis 7 (interno, sesiones SSE + cache)
  qdrant:       Qdrant (interno, vectores)
  ollama:       Ollama (interno, LLM local)
  frontend:     Angular/nginx 80 (público)

networks:
  public:       api, frontend
  internal:     api, worker, mysql, redis, qdrant, ollama
```
