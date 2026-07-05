-- Migración 008: pipeline relacional + trazabilidad
-- Alinea el esquema con los prompts nuevos de los agentes:
--   * id_norma (FK snake_case) para cruzar normas ↔ responsabilidades ↔ brechas ↔ matriz
--   * origen_contexto (frase/sección del plan que originó cada dato) para trazabilidad
--   * recomendacion y tipo_detallado en brechas (mitigación + tipo jurídico fino)
--   * sector y origen_contexto en la matriz
--
-- NOTA: sintaxis MySQL 8 (ALTER plano, sin IF NOT EXISTS). Ejecutar UNA sola vez.

-- ── Normas ──────────────────────────────────────────────────────────────────
ALTER TABLE plan_normas
  ADD COLUMN id_norma        VARCHAR(100) NULL COMMENT 'FK relacional snake_case (ej: ley_715_2001)' AFTER plan_id,
  ADD COLUMN origen_contexto TEXT NULL COMMENT 'Frase/sección del plan donde se aplica la norma' AFTER extracto,
  ADD INDEX idx_norma_id_norma (id_norma);

-- ── Responsabilidades ───────────────────────────────────────────────────────
ALTER TABLE responsabilidades
  ADD COLUMN origen_contexto TEXT NULL COMMENT 'Meta/programa/frase del plan que origina la responsabilidad' AFTER referencia_legal;

-- ── Actores ─────────────────────────────────────────────────────────────────
ALTER TABLE plan_actores
  ADD COLUMN origen_contexto TEXT NULL COMMENT 'Frase/programa del plan donde se nombra al actor' AFTER sector;

-- ── Brechas ─────────────────────────────────────────────────────────────────
ALTER TABLE brechas
  ADD COLUMN tipo_detallado  VARCHAR(50) NULL COMMENT 'Tipo jurídico: riesgo_disciplinario|desarmonizacion|vacio_competencia|duplicidad_ilegal' AFTER referencia_legal,
  ADD COLUMN recomendacion   TEXT NULL COMMENT 'Instrucción de mitigación para corregir el plan' AFTER tipo_detallado,
  ADD COLUMN origen_contexto TEXT NULL COMMENT 'Línea/sección del plan donde se evidencia la falla' AFTER recomendacion;

-- ── Matriz de competencias ──────────────────────────────────────────────────
ALTER TABLE matriz_competencias
  ADD COLUMN sector          VARCHAR(120) NULL COMMENT 'Sector DNP-KPT de la competencia' AFTER brecha,
  ADD COLUMN origen_contexto TEXT NULL COMMENT 'Fragmento del plan que activó la fila de la matriz' AFTER sector;
