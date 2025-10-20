CREATE TABLE IF NOT EXISTS sombra_poligono (
  id BIGSERIAL PRIMARY KEY,
  geom geometry(Polygon,4326)
);
CREATE INDEX IF NOT EXISTS idx_sombra_poligono_geom ON sombra_poligono USING GIST (geom);

CREATE TABLE IF NOT EXISTS via_sombreada (
  id BIGSERIAL PRIMARY KEY,
  geom geometry(LineString,4326)
);
CREATE INDEX IF NOT EXISTS idx_via_sombreada_geom ON via_sombreada USING GIST (geom);
