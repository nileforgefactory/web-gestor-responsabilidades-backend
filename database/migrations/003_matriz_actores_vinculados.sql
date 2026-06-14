-- ═══════════════════════════════════════════════════════════════════════
--  Migración 003: Agregar actores_vinculados a matriz_competencias
--  Almacena JSON [{nombre, nivel, tipo}] del cruce actor↔competencia
-- ═══════════════════════════════════════════════════════════════════════

USE gestor_responsabilidades;

ALTER TABLE matriz_competencias
    ADD COLUMN actores_vinculados TEXT NULL AFTER brecha;
