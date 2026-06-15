-- Migración 009: campo 'actor' en la matriz de competencias
-- Convierte la matriz en un modelo relacional (competencia, actor): cada fila
-- mapea una competencia a un actor titular específico, alimentando las vistas
-- "Territorial" y "Por Actores". En duplicidad se generan filas independientes
-- por actor.
--
-- NOTA: sintaxis MySQL 8 (ALTER plano). Ejecutar UNA sola vez.

ALTER TABLE matriz_competencias
  ADD COLUMN actor VARCHAR(300) NULL
    COMMENT 'Actor titular de la competencia (clave relacional de la vista Por Actores)'
    AFTER competencia;
