INSERT INTO via_arista (geom,length_m,osm_id,oneway,highway)
SELECT s.geom, s.length_m, s.osm_id, s.oneway, s.highway
FROM (
  SELECT DISTINCT ON (ST_AsBinary(geom)) geom, length_m, osm_id, oneway, highway
  FROM via_arista_stg
) AS s
LEFT JOIN via_arista v
  ON ST_Equals(v.geom, s.geom)
WHERE v.id IS NULL;

TRUNCATE via_arista_stg;
