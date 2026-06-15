-- Migración 010: amplía el ENUM de plan_normas.tipo
-- La columna solo aceptaba ('ley','decreto','resolucion','circular','otro'), pero el
-- pipeline clasifica normas como conpes, acuerdo, ordenanza, política o sentencia.
-- Al insertar uno de esos valores MySQL truncaba (error 1265) y rompía el guardado.
--
-- NOTA: sintaxis MySQL 8. Ejecutar UNA sola vez.

ALTER TABLE plan_normas
  MODIFY COLUMN tipo
    ENUM('ley','decreto','resolucion','circular','politica','conpes','ordenanza','acuerdo','sentencia','otro')
    DEFAULT 'ley';
