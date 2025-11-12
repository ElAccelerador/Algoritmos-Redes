#!/usr/bin/env bash
set -euo pipefail

echo "[1/6] Levantando stack (db, app, web)…"
docker compose up -d --build

echo "[2/6] Ejecutando ETL (amenazas y metadata) en contenedor 'app'…"
# --- Amenazas (Siempre se descargan) ---
docker compose exec app python3 etl/amenazas/extract_openmeteo_temp_grid.py
docker compose exec app python3 etl/amenazas/extract_openweather_uv_grid.py

# --- CORRECCIÓN: Lógica de caché para Edificios (tu idea) ---
BUILDINGS_FILE="json/metadata_edificios.geojson"
if [ -f "$BUILDINGS_FILE" ]; then
    echo "[INFO] $BUILDINGS_FILE ya existe, saltando descarga de edificios."
else
    echo "[INFO] $BUILDINGS_FILE no encontrado. Descargando desde Overpass API..."
    docker compose exec app python3 etl/metadata/edificios/extract_osm_buildings.py
fi
# --- Fin de la corrección ---

docker compose exec app python3 etl/sombra/build_shadow_roads.py || echo "[WARN] sombras opcional"

echo "[3/6] Creando tablas base (schema ya fue auto-cargado por initdb)..."
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f /data/db_scripts/load/load_bebederos.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f /data/db_scripts/load/load_edificios.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f /data/db_scripts/load/load_amenaza_calor_grid.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f /data/db_scripts/load/load_amenaza_uv_grid.sql
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f /data/db_scripts/load/load_sombras.sql

echo "[4/6] Cargando GeoJSON → PostGIS (ogr2ogr en el contenedor db)…"
# Infraestructura
for f in infra_provi_sector.geojson infra_provi_sector_south.geojson infra_provi_sector_south_exp.geojson infra_provi_sector_east.geojson; do
  if [ -s "json/$f" ]; then
    docker compose exec -T db ogr2ogr -f PostgreSQL PG:"host=localhost dbname=gis user=postgres password=postgres" \
      /data/json/$f -nln via_arista_stg -nlt LINESTRING -lco GEOMETRY_NAME=geom $(test "$f" = "infra_provi_sector.geojson" && echo -overwrite || echo -append)
  fi
done
# Carga y crea topología
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f /data/db_scripts/load/load_infra.sql

# Añade columnas de costo a la tabla de aristas
echo "[4.1/6] Añadiendo columnas de costo (Fase 3) a via_arista..."
docker compose exec -T db psql -U postgres -d gis -v ON_ERROR_STOP=1 -f /data/db_scripts/load/005_fase3_alter_aristas.sql

# Carga de otros GeoJSON (Bebederos, Edificios, etc.)
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
# Sombras
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
docker compose exec -T db psql -U postgres -d gis -c "SELECT hora, COUNT(*) celdas_uv FROM amenaza_uv_grid GROUP BY hora ORDER BY hora;"
docker compose exec -T db psql -U postgres -d gis -c "SELECT hora, COUNT(*) celdas_temp FROM amenaza_calor_grid GROUP BY hora ORDER BY hora;"

echo "[6/6] Listo."
echo "Web:    http://localhost:8080/index.html"
echo "API:    http://localhost:8000/health"
echo "Ruta:   http://localhost:8000/route-fase2-dijkstra-distancia?src=-33.445,-70.66&dst=-33.425,-70.635"
