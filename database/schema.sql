-- ═══════════════════════════════════════════════════════════════════════
--  Gestor de Responsabilidades — MySQL Schema v1.0
--  Motor: MySQL 8.0+  |  Charset: utf8mb4
-- ═══════════════════════════════════════════════════════════════════════

CREATE DATABASE IF NOT EXISTS gestor_responsabilidades
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE gestor_responsabilidades;

-- ── PLANES ───────────────────────────────────────────────────────────────
--  Representa cada plan de desarrollo analizado (nacional, dpto, municipal,
--  sectorial). qdrant_doc_id vincula al documento vectorizado en Qdrant.
CREATE TABLE planes (
    id              VARCHAR(36)   PRIMARY KEY,
    titulo          VARCHAR(500)  NOT NULL,
    nombre_corto    VARCHAR(100),
    entidad         VARCHAR(300),
    entidad_icono   VARCHAR(10)   DEFAULT '🏛️',
    nivel           ENUM('nacional','departamental','municipal','sectorial') NOT NULL,
    periodo         VARCHAR(50),
    estado          ENUM('cargando','analizando','analizado','en-proceso','archivado') DEFAULT 'cargando',
    descripcion     TEXT,
    archivo_nombre  VARCHAR(500),
    qdrant_doc_id   VARCHAR(100),          -- document_id en la colección Qdrant "planes"
    resp_total      INT           DEFAULT 0,
    leyes_total     INT           DEFAULT 0,
    actores_total   INT           DEFAULT 0,
    brechas_total   INT           DEFAULT 0,
    avance_pct      DECIMAL(5,2)  DEFAULT 0,
    creado_en       DATETIME      DEFAULT CURRENT_TIMESTAMP,
    actualizado_en  DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_nivel  (nivel),
    INDEX idx_estado (estado)
) ENGINE=InnoDB;

-- ── COBERTURA DE SECTORES POR PLAN ───────────────────────────────────────
CREATE TABLE plan_sectores (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    plan_id        VARCHAR(36)   NOT NULL,
    sector         VARCHAR(200)  NOT NULL,
    icono          VARCHAR(10),
    cobertura_pct  DECIMAL(5,2)  DEFAULT 0,
    FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE CASCADE,
    INDEX idx_plan (plan_id)
) ENGINE=InnoDB;

-- ── ACTORES IDENTIFICADOS EN EL PLAN ────────────────────────────────────
CREATE TABLE plan_actores (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    plan_id        VARCHAR(36)   NOT NULL,
    nombre         VARCHAR(300)  NOT NULL,
    tipo           ENUM('principal','concurrente','subsidiario','otro') DEFAULT 'otro',
    icono          VARCHAR(10),
    resp_count     INT           DEFAULT 0,
    badge_label    VARCHAR(100),
    badge_variant  VARCHAR(20)   DEFAULT 'blue',
    destacado      BOOLEAN       DEFAULT FALSE,
    FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE CASCADE,
    INDEX idx_plan (plan_id)
) ENGINE=InnoDB;

-- ── RESPONSABILIDADES EXTRAÍDAS ──────────────────────────────────────────
--  tipo: P=Principal, C=Concurrente, S=Subsidiario, N=No asignado
CREATE TABLE responsabilidades (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    plan_id          VARCHAR(36)   NOT NULL,
    titulo           VARCHAR(500)  NOT NULL,
    descripcion      TEXT,
    sector           VARCHAR(200),
    tipo             ENUM('P','C','S','N') DEFAULT 'P',
    referencia_legal VARCHAR(200),
    icono            VARCHAR(10)   DEFAULT '✅',
    FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE CASCADE,
    INDEX idx_plan   (plan_id),
    INDEX idx_sector (sector)
) ENGINE=InnoDB;

-- ── BRECHAS / GAPS DETECTADOS ────────────────────────────────────────────
CREATE TABLE brechas (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    plan_id          VARCHAR(36)   NOT NULL,
    titulo           VARCHAR(500)  NOT NULL,
    descripcion      TEXT,
    tipo             ENUM('critica','duplicidad','indefinido','sin_responsable') DEFAULT 'critica',
    severidad        ENUM('alta','media','baja') DEFAULT 'alta',
    referencia_legal VARCHAR(200),
    icono            VARCHAR(10)   DEFAULT '🚨',
    FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE CASCADE,
    INDEX idx_plan (plan_id)
) ENGINE=InnoDB;

-- ── MATRIZ DE COMPETENCIAS ───────────────────────────────────────────────
--  Columnas P/C/S/N: Principal / Concurrente / Subsidiario / No aplica
CREATE TABLE matriz_competencias (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    plan_id        VARCHAR(36)   NOT NULL,
    competencia    VARCHAR(300)  NOT NULL,
    ley_base       VARCHAR(200),
    nacion         ENUM('P','C','S','N') DEFAULT 'N',
    departamento   ENUM('P','C','S','N') DEFAULT 'N',
    municipio      ENUM('P','C','S','N') DEFAULT 'N',
    especializado  ENUM('P','C','S','N') DEFAULT 'N',
    brecha         ENUM('ok','critica','duplicidad','indefinido') DEFAULT 'ok',
    FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE CASCADE,
    INDEX idx_plan (plan_id)
) ENGINE=InnoDB;

-- ── NORMAS / LEYES APLICABLES POR PLAN ──────────────────────────────────
CREATE TABLE plan_normas (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    plan_id          VARCHAR(36)   NOT NULL,
    norma_codigo     VARCHAR(100),
    titulo           VARCHAR(500)  NOT NULL,
    articulos        VARCHAR(200),
    extracto         TEXT,
    tipo             ENUM('ley','decreto','resolucion','circular','otro') DEFAULT 'ley',
    vigente          BOOLEAN       DEFAULT TRUE,
    advertencia      VARCHAR(300),
    relevancia       INT           DEFAULT 80,   -- score 0–100
    FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE CASCADE,
    INDEX idx_plan (plan_id),
    INDEX idx_tipo (tipo)
) ENGINE=InnoDB;

-- ── BASE DE CONOCIMIENTO RAG ─────────────────────────────────────────────
--  Registro de documentos legales indexados en Qdrant (colección "normas_legales").
--  qdrant_doc_id corresponde al document_id utilizado en la ingesta.
CREATE TABLE base_conocimiento (
    id              VARCHAR(36)   PRIMARY KEY,
    nombre          VARCHAR(500)  NOT NULL,
    tipo            ENUM('ley','decreto','resolucion','circular','pdf','texto','otro') DEFAULT 'otro',
    coleccion_id    VARCHAR(100)  DEFAULT 'normas_legales',
    descripcion     TEXT,
    territorio      TEXT          COMMENT 'JSON [País, Departamento, Municipio]',
    archivo_nombre  VARCHAR(500),
    archivo_tamano  BIGINT,                      -- bytes
    qdrant_doc_id   VARCHAR(100),
    chunk_count     INT           DEFAULT 0,
    estado          ENUM('pendiente','procesando','indexado','error') DEFAULT 'pendiente',
    error_mensaje   TEXT,
    creado_en       DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_estado (estado),
    INDEX idx_tipo   (tipo),
    INDEX idx_coleccion (coleccion_id)
) ENGINE=InnoDB;

-- ── HISTORIAL DE BÚSQUEDAS RAG ───────────────────────────────────────────
CREATE TABLE historial_busqueda (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    consulta        TEXT          NOT NULL,
    resultado_count INT           DEFAULT 0,
    filtros         JSON,
    usando_api_real BOOLEAN       DEFAULT FALSE,
    creado_en       DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_fecha (creado_en)
) ENGINE=InnoDB;

-- ── LOG DE INGESTA ───────────────────────────────────────────────────────
--  Auditoría de cada operación de carga (plan o documento de conocimiento).
CREATE TABLE log_ingesta (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    tipo            ENUM('plan','conocimiento')  NOT NULL,
    referencia_id   VARCHAR(36),                -- plan_id o base_conocimiento.id
    archivo_nombre  VARCHAR(500),
    archivo_tamano  BIGINT,
    chunk_count     INT,
    estado          ENUM('pendiente','procesando','completado','error') DEFAULT 'pendiente',
    error_mensaje   TEXT,
    duracion_ms     INT,
    creado_en       DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tipo_ref (tipo, referencia_id),
    INDEX idx_estado   (estado)
) ENGINE=InnoDB;
