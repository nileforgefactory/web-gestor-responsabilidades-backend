-- Ejecutar una vez si base_conocimiento ya existía sin la columna territorio.
USE gestor_responsabilidades;

ALTER TABLE base_conocimiento
  ADD COLUMN IF NOT EXISTS territorio TEXT NULL
    COMMENT 'JSON [País, Departamento, Municipio]'
  AFTER descripcion;
