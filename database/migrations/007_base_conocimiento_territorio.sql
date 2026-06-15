-- Migración 007: agrega columna territorio a base_conocimiento
ALTER TABLE base_conocimiento
  ADD COLUMN IF NOT EXISTS territorio TEXT NULL
    COMMENT 'JSON [País, Departamento, Municipio]'
    AFTER archivo_tamano;
