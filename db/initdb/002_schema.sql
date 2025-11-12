-- ===================================
-- INFRAESTRUCTURA (Tablas Faltantes)
-- ===================================

-- 1. Tabla STAGING (temporal) para ogr2ogr
CREATE TABLE IF NOT EXISTS via_arista_stg (
    id SERIAL PRIMARY KEY,
    geom geometry(LineString, 4326),
    osm_id BIGINT,
    highway TEXT,
    oneway TEXT,
    length_m REAL
);

-- 2. Tabla FINAL de aristas
CREATE TABLE IF NOT EXISTS via_arista (
    id BIGINT PRIMARY KEY, -- id del edge, usado por pgRouting
    geom geometry(LineString, 4326),
    osm_id BIGINT,
    highway TEXT,
    length_m REAL,
    source BIGINT, -- id del nodo origen (para pgRouting)
    target BIGINT, -- id del nodo destino (para pgRouting)
    cost REAL, -- costo base (longitud)
    reverse_cost REAL
);
CREATE INDEX IF NOT EXISTS idx_via_arista_geom ON via_arista USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_via_arista_source ON via_arista (source);
CREATE INDEX IF NOT EXISTS idx_via_arista_target ON via_arista (target);

-- 3. Tabla FINAL de nodos (creada por load_infra.sql)
CREATE TABLE IF NOT EXISTS via_nodo (
    id BIGINT PRIMARY KEY, -- id del vértice
    geom geometry(Point, 4326)
);
CREATE INDEX IF NOT EXISTS idx_via_nodo_geom ON via_nodo USING GIST (geom);


-- ===================================
-- METADATA
-- ===================================

-- 4. Metadata: Bebederos
CREATE TABLE IF NOT EXISTS bebedero (
    id SERIAL PRIMARY KEY,
    geom geometry(Point, 4326),
    fuente TEXT,
    osm_id BIGINT
);
CREATE INDEX IF NOT EXISTS idx_bebedero_geom ON bebedero USING GIST (geom);

-- 5. Metadata: Edificios
CREATE TABLE IF NOT EXISTS edificio (
    id SERIAL PRIMARY KEY,
    geom geometry(Polygon, 4326),
    osm_id BIGINT,
    tipo TEXT,
    height_m REAL
);
CREATE INDEX IF NOT EXISTS idx_edificio_geom ON edificio USING GIST (geom);

-- ===================================
-- AMENAZAS
-- ===================================

-- 6. Amenaza: Vías Sombreadas
CREATE TABLE IF NOT EXISTS via_sombreada (
    id SERIAL PRIMARY KEY,
    geom geometry(LineString, 4326),
    shaded BOOLEAN DEFAULT true
);
CREATE INDEX IF NOT EXISTS idx_via_sombreada_geom ON via_sombreada USING GIST (geom);

-- 7. Amenaza: Polígonos de Sombra
CREATE TABLE IF NOT EXISTS sombra_poligono (
    id SERIAL PRIMARY KEY,
    geom geometry(Polygon, 4326)
);
CREATE INDEX IF NOT EXISTS idx_sombra_poligono_geom ON sombra_poligono USING GIST (geom);

-- 8. Amenaza: Calor
CREATE TABLE IF NOT EXISTS amenaza_calor_grid (
    id SERIAL PRIMARY KEY,
    geom geometry(Polygon, 4326),
    temp_c REAL,
    "row" INT,
    "col" INT
);
CREATE INDEX IF NOT EXISTS idx_calor_grid_geom ON amenaza_calor_grid USING GIST (geom);

-- 9. Amenaza: UV
CREATE TABLE IF NOT EXISTS amenaza_uv_grid (
    id SERIAL PRIMARY KEY,
    geom geometry(Polygon, 4326),
    uv_index REAL,
    "row" INT,
    "col" INT,
    timestamp BIGINT
);
CREATE INDEX IF NOT EXISTS idx_uv_grid_geom ON amenaza_uv_grid USING GIST (geom);
