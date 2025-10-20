-- Infraestructura base
CREATE TABLE IF NOT EXISTS via_arista (
  id BIGSERIAL PRIMARY KEY,
  source BIGINT,
  target BIGINT,
  geom geometry(LineString,4326),
  length_m REAL,
  osm_id BIGINT,
  oneway BOOLEAN,
  highway TEXT
);
CREATE INDEX IF NOT EXISTS idx_via_arista_geom ON via_arista USING GIST (geom);

CREATE TABLE IF NOT EXISTS via_arista_stg (
  geom geometry(LineString,4326),
  length_m REAL,
  osm_id BIGINT,
  oneway BOOLEAN,
  highway TEXT
);
CREATE INDEX IF NOT EXISTS idx_via_arista_stg_geom ON via_arista_stg USING GIST (geom);
