-- db/schema.sql (ajuste mínimo recomendado)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

-- via_arista con id autogenerado para evitar colisiones entre teselas
CREATE TABLE IF NOT EXISTS via_arista (
  id BIGSERIAL PRIMARY KEY,
  source BIGINT,
  target BIGINT,
  geom geometry(LineString, 4326),
  length_m REAL,
  osm_id BIGINT,
  oneway BOOLEAN,
  highway TEXT
);
CREATE INDEX IF NOT EXISTS idx_via_arista_geom   ON via_arista USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_via_arista_osm    ON via_arista(osm_id);

-- staging para cargas por tesela
CREATE TABLE IF NOT EXISTS via_arista_stg (
  geom geometry(LineString, 4326),
  length_m REAL,
  osm_id BIGINT,
  oneway BOOLEAN,
  highway TEXT
);
CREATE INDEX IF NOT EXISTS idx_via_arista_stg_geom ON via_arista_stg USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_via_arista_stg_osm  ON via_arista_stg(osm_id);
