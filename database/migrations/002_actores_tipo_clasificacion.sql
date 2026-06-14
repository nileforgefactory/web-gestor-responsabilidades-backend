-- ═══════════════════════════════════════════════════════════════════════
--  Migración 002: Actualizar clasificación de tipos de actores
--  Sustituye principal/concurrente/subsidiario por categorías funcionales
--  según estándares de planes de desarrollo en Colombia
-- ═══════════════════════════════════════════════════════════════════════

USE gestor_responsabilidades;

-- 1. Ampliar ENUM conservando valores legados para permitir la migración de datos
ALTER TABLE plan_actores
    MODIFY COLUMN tipo ENUM(
        'ejecutor','beneficiario','financiador','coordinador','regulador',
        'aliado','operador','supervisor','tomador_decision','participante',
        'apoyo_tecnico','control','otro',
        'principal','concurrente','subsidiario'
    ) DEFAULT 'otro';

-- 2. Migrar valores legados a sus equivalentes funcionales
UPDATE plan_actores SET tipo = 'ejecutor'    WHERE tipo = 'principal';
UPDATE plan_actores SET tipo = 'coordinador' WHERE tipo = 'concurrente';
UPDATE plan_actores SET tipo = 'aliado'      WHERE tipo = 'subsidiario';

-- 3. Eliminar valores legados del ENUM (ya no hay datos con esos valores)
ALTER TABLE plan_actores
    MODIFY COLUMN tipo ENUM(
        'ejecutor','beneficiario','financiador','coordinador','regulador',
        'aliado','operador','supervisor','tomador_decision','participante',
        'apoyo_tecnico','control','otro'
    ) DEFAULT 'otro';
