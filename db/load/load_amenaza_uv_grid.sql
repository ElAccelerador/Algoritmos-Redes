CREATE TABLE IF NOT EXISTS amenaza_uv_grid (
  id BIGSERIAL PRIMARY KEY,
  uv_index REAL,
  row INTEGER,
  col INTEGER,
  centroid_lon DOUBLE PRECISION,
  centroid_lat DOUBLE PRECISION,
  geom geometry(Polygon,4326)
);
CREATE INDEX IF NOT EXISTS idx_amenaza_uv_grid_geom ON amenaza_uv_grid USING GIST (geom);
