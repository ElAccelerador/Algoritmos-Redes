-- 1. Modificar tabla de Temperatura
ALTER TABLE amenaza_calor_grid ADD COLUMN hora INT;

-- 2. Modificar tabla de UV
ALTER TABLE amenaza_uv_grid ADD COLUMN hora INT;

-- 3. Modificar tabla de Polígonos de Sombra
ALTER TABLE sombra_poligono ADD COLUMN hora INT;

-- 4. Modificar tabla de Vías Sombreadas
ALTER TABLE via_sombreada ADD COLUMN hora INT;

-- 5. Re-crear índices para consultas espacio-temporales
DROP INDEX IF EXISTS idx_calor_grid_geom;
DROP INDEX IF EXISTS idx_uv_grid_geom;
DROP INDEX IF EXISTS idx_sombra_poligono_geom;
DROP INDEX IF EXISTS idx_via_sombreada_geom;

CREATE INDEX idx_calor_grid_geom_hora ON amenaza_calor_grid USING GIST (geom, hora);
CREATE INDEX idx_uv_grid_geom_hora ON amenaza_uv_grid USING GIST (geom, hora);
CREATE INDEX idx_sombra_poligono_geom_hora ON sombra_poligono USING GIST (geom, hora);
CREATE INDEX idx_via_sombreada_geom_hora ON via_sombreada USING GIST (geom, hora);

-- FIN DEL ARCHIVO -- (No incluyas el "ALTER TABLE via_arista" aquí)
