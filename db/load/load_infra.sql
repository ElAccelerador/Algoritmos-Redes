-- importa a via_arista_stg con ogr2ogr antes de ejecutar esto
INSERT INTO via_arista (geom,length_m,osm_id,oneway,highway)
SELECT s.geom, s.length_m, s.osm_id, s.oneway, s.highway
FROM (
  SELECT DISTINCT ON (ST_AsBinary(geom)) geom, length_m, osm_id, oneway, highway
  FROM via_arista_stg
) s
LEFT JOIN via_arista v ON ST_Equals(v.geom, s.geom)
WHERE v.id IS NULL;

TRUNCATE via_arista_stg;

CREATE EXTENSION IF NOT EXISTS pgrouting;
SELECT pgr_createTopology('via_arista', 0.00001, 'geom', 'id', 'source', 'target');
SELECT pgr_analyzeGraph('via_arista', 0.00001, 'geom', 'id');

DROP TABLE IF EXISTS via_nodo;
CREATE TABLE via_nodo AS
  SELECT id::bigint, the_geom::geometry(Point,4326) AS geom,
         NULL::real AS elev_m, NULL::bigint AS osm_id
  FROM via_arista_vertices_pgr;
CREATE INDEX IF NOT EXISTS idx_via_nodo_geom ON via_nodo USING GIST (geom);
