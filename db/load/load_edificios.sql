CREATE TABLE IF NOT EXISTS edificio (
  id BIGSERIAL PRIMARY KEY,
  osm_id BIGINT,
  height_m REAL,
  geom geometry(Polygon,4326)
);
CREATE INDEX IF NOT EXISTS idx_edificio_geom ON edificio USING GIST (geom);
