CREATE TABLE IF NOT EXISTS bebedero (
  id BIGSERIAL PRIMARY KEY,
  fuente TEXT,
  attrs JSONB,
  geom geometry(Point,4326)
);
CREATE INDEX IF NOT EXISTS idx_bebedero_geom ON bebedero USING GIST (geom);
