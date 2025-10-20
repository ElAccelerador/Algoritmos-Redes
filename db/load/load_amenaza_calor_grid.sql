CREATE TABLE IF NOT EXISTS amenaza_calor_grid (
  id BIGSERIAL PRIMARY KEY,
  temp_c REAL,
  row INTEGER,
  col INTEGER,
  centroid_lon DOUBLE PRECISION,
  centroid_lat DOUBLE PRECISION,
  geom geometry(Polygon,4326)
);
CREATE INDEX IF NOT EXISTS idx_amenaza_calor_grid_geom ON amenaza_calor_grid USING GIST (geom);
