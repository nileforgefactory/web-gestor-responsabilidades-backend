-- Migración 004: agregar nivel, sector y competencias a plan_actores
ALTER TABLE plan_actores
    ADD COLUMN nivel        VARCHAR(50)  NULL AFTER tipo,
    ADD COLUMN sector       VARCHAR(200) NULL AFTER nivel,
    ADD COLUMN competencias TEXT         NULL AFTER sector;
