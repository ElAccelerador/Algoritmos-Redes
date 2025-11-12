-- 6. Añadir columnas de costo a la tabla de aristas (para Fase 3)
-- Se ejecuta DESPUÉS de que load_infra.sql cree via_arista
ALTER TABLE via_arista
ADD COLUMN IF NOT EXISTS costo_calor DOUBLE PRECISION DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS costo_uv DOUBLE PRECISION DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS costo_sombra DOUBLE PRECISION DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS costo_final DOUBLE PRECISION DEFAULT 0.0;
