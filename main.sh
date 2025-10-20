#!/usr/bin/env bash
set -euo pipefail

echo "[1/6] Levantando stack (db, app, web)…"
docker compose up -d --build

echo "[2/6] Ejecutando ETL (amenazas y metadata) en host…"
# NOTA: Infraestructura ya la tienes en json/. Si quisieras re-extraer, llama a tus extract_*.py aquí.
python3 etl/amenazas/extract_openmeteo_temp_grid.py
python3 etl/amenazas/extract_openweather_uv_grid.py
python3 etl/metadata/edificios/extract_osm_buildings.py
python3 etl/sombra/build_shadow_roads.py || echo "[WARN] sombras opcional"

echo "[3/6] Creando tablas base…"
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f db/initdb/002_schema.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f db/load/load_bebederos.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f db/load/load_edificios.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f db/load/load_amenaza_calor_grid.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f db/load/load_amenaza_uv_grid.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f db/load/load_sombras.sql

echo "[4/6] Cargando GeoJSON → PostGIS (ogr2ogr en el contenedor db)…"
# Infraestructura -> via_arista_stg (append múltiple) y merge a via_arista
for f in infra_provi_sector.geojson infra_provi_sector_south.geojson infra_provi_sector_south_exp.geojson infra_provi_sector_east.geojson; do
  if [ -s "json/$f" ]; then
    docker compose exec -T db ogr2ogr -f PostgreSQL PG:"host=localhost dbname=gis user=postgres password=postgres" \
      /data/json/$f -nln via_arista_stg -nlt LINESTRING -lco GEOMETRY_NAME=geom $(test "$f" = "infra_provi_sector.geojson" && echo -overwrite || echo -append)
  fi
done
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f db/load/load_infra.sql

# Bebederos
if [ -s json/metadata_bebederos.geojson ]; then
  docker compose exec -T db ogr2ogr -f PostgreSQL PG:"host=localhost dbname=gis user=postgres password=postgres" \
    /data/json/metadata_bebederos.geojson -nln bebedero -nlt POINT -lco GEOMETRY_NAME=geom -overwrite
fi
# Edificios
if [ -s json/metadata_edificios.geojson ]; then
  docker compose exec -T db ogr2ogr -f PostgreSQL PG:"host=localhost dbname=gis user=postgres password=postgres" \
    /data/json/metadata_edificios.geojson -nln edificio -nlt POLYGON -lco GEOMETRY_NAME=geom -overwrite
fi
# Temperatura
if [ -s json/amenaza_temp_grid.geojson ]; then
  docker compose exec -T db ogr2ogr -f PostgreSQL PG:"host=localhost dbname=gis user=postgres password=postgres" \
    /data/json/amenaza_temp_grid.geojson -nln amenaza_calor_grid -nlt POLYGON -lco GEOMETRY_NAME=geom -overwrite
fi
# UV
if [ -s json/amenaza_uv_grid.geojson ]; then
  docker compose exec -T db ogr2ogr -f PostgreSQL PG:"host=localhost dbname=gis user=postgres password=postgres" \
    /data/json/amenaza_uv_grid.geojson -nln amenaza_uv_grid -nlt POLYGON -lco GEOMETRY_NAME=geom -overwrite
fi
# Sombras (opcional)
if [ -s json/sombra_poligonos.geojson ]; then
  docker compose exec -T db ogr2ogr -f PostgreSQL PG:"host=localhost dbname=gis user=postgres password=postgres" \
    /data/json/sombra_poligonos.geojson -nln sombra_poligono -nlt POLYGON -lco GEOMETRY_NAME=geom -overwrite
fi
if [ -s json/infra_sombreada.geojson ]; then
  docker compose exec -T db ogr2ogr -f PostgreSQL PG:"host=localhost dbname=gis user=postgres password=postgres" \
    /data/json/infra_sombreada.geojson -nln via_sombreada -nlt LINESTRING -lco GEOMETRY_NAME=geom -overwrite
fi

echo "[5/6] Verificación rápida…"
docker compose exec -T db psql -U postgres -d gis -c "SELECT COUNT(*) vias FROM via_arista;"
docker compose exec -T db psql -U postgres -d gis -c "SELECT COUNT(*) nodos FROM via_nodo;"
docker compose exec -T db psql -U postgres -d gis -c "SELECT COUNT(*) bebederos FROM bebedero;"
docker compose exec -T db psql -U postgres -d gis -c "SELECT COUNT(*) edificios FROM edificio;"
docker compose exec -T db psql -U postgres -d gis -c "SELECT COUNT(*) uv_celdas FROM amenaza_uv_grid;"
docker compose exec -T db psql -U postgres -d gis -c "SELECT COUNT(*) temp_celdas FROM amenaza_calor_grid;"

echo "[6/6] Listo."
echo "Web:   http://localhost:8080/index.html"
echo "API:   http://localhost:8000/health"
echo "Ruta:  http://localhost:8000/route?src=-33.445,-70.66&dst=-33.425,-70.635"
