-- Migración 006: agrega estado 'deshabilitado' a base_conocimiento
ALTER TABLE base_conocimiento
  MODIFY COLUMN estado ENUM('pendiente','procesando','indexado','error','deshabilitado')
    NOT NULL DEFAULT 'pendiente';
