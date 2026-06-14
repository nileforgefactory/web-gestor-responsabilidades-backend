-- Migración 005: tabla puente actor_competencias
-- Un actor puede ejecutar N competencias; cada competencia puede tener varios actores.

CREATE TABLE actor_competencias (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    plan_id    VARCHAR(36)  NOT NULL,
    actor_id   INT          NOT NULL,
    titulo     VARCHAR(500) NOT NULL,
    sector     VARCHAR(200) NULL,
    FOREIGN KEY (plan_id)  REFERENCES planes(id)       ON DELETE CASCADE,
    FOREIGN KEY (actor_id) REFERENCES plan_actores(id) ON DELETE CASCADE,
    INDEX idx_actor (actor_id),
    INDEX idx_plan  (plan_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Eliminar la columna competencias (texto plano) que queda obsoleta
ALTER TABLE plan_actores DROP COLUMN competencias;
