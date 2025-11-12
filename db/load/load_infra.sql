-- 1. Mover desde STG a tabla final, asignando ID y calculando costos
-- (Esta es la versión para peatones, bidireccional)
INSERT INTO via_arista (
    id, geom, length_m, osm_id, highway,
    cost, reverse_cost
)
SELECT
    COALESCE(s.osm_id, s.id + 1000000000) AS id,
    s.geom,
    COALESCE(s.length_m, ST_Length(s.geom::geography)) AS length_m,
    s.osm_id,
    s.highway,
    COALESCE(s.length_m, ST_Length(s.geom::geography)) AS cost,
    COALESCE(s.length_m, ST_Length(s.geom::geography)) AS reverse_cost
FROM via_arista_stg s
ON CONFLICT (id) DO NOTHING;

-- 2. Crear Topología
-- ¡ESTO CREA LA TABLA 'via_arista_vertices_pgr'!
SELECT pgr_createTopology('via_arista', 0.000135, 'geom', 'id', 'source', 'target', 'true', clean := false);

-- 3. Analizar la red (opcional pero recomendado)
SELECT pgr_analyzeGraph('via_arista', 0.000135, 'geom', 'id', 'source', 'target');

-- 4. Crear la tabla de nodos (para referencia futura)
DROP TABLE IF EXISTS via_nodo;
CREATE TABLE via_nodo AS
SELECT
    id,
    the_geom as geom
FROM via_arista_vertices_pgr; -- (Ahora esto funciona, porque la tabla existe)

CREATE INDEX idx_via_nodo_geom_nodo ON via_nodo USING GIST (geom);

-- 5. Añadir columna 'geom' a la tabla de vértices
-- (Esto es lo que main.sh [6.1/6] intentaba hacer)
ALTER TABLE via_arista_vertices_pgr ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);

-- 6. Poblar la columna 'geom' (usada por server.py)
UPDATE via_arista_vertices_pgr v SET geom = n.geom FROM via_nodo n WHERE v.id = n.id;
