import os, time, sys
import json
from contextlib import contextmanager
from datetime import datetime

import psycopg
from psycopg import sql # Importante para formatear SQL de forma segura
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# --- Configuración (sin cambios) ---
DB_HOST = os.environ.get("DB_HOST", "db")
DB_NAME = os.environ.get("DB_NAME", "gis")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "postgres")
DB_DSN = f"host={DB_HOST} dbname={DB_NAME} user={DB_USER} password={DB_PASS}"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Gestor de Conexión (sin cambios) ---
@contextmanager
def get_db_conn():
    conn = None
    try:
        conn = psycopg.connect(DB_DSN)
        yield conn
    except Exception as e:
        print(f"Error de conexión a la BD: {e}", file=sys.stderr)
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {e}")
    finally:
        if conn: conn.close()

# --- Helper: Encontrar Nodo (sin cambios) ---
SQL_FIND_NEAREST_NODE = """
    SELECT id, ST_X(geom), ST_Y(geom)
    FROM via_arista_vertices_pgr
    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
    LIMIT 1;
"""
def find_nearest_node(conn, lon, lat):
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_FIND_NEAREST_NODE, (lon, lat))
            result = cur.fetchone()
            if result:
                return result[0], result[1], result[2] # id (bigint), x (float), y (float)
            else:
                return None, None, None
    except Exception as e:
        print(f"Error en find_nearest_node: {e}", file=sys.stderr)
        raise HTTPException(status_code=422, detail=f"No se pudo encontrar un nodo de red cercano: {e}")

# --- Helper: Formato GeoJSON (sin cambios) ---
def format_route_as_geojson(route_geom_list, total_cost, time_ms):
    if not route_geom_list:
        return {"type": "FeatureCollection", "features": [], "properties": {}}
    features = [
        {
            "type": "Feature",
            "geometry": json.loads(geom_json),
            "properties": {}
        }
        for geom_json in route_geom_list
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "total_cost_meters": total_cost,
            "compute_time_ms": round(time_ms, 3)
        }
    }

# ===================================================================
# 📍 ENDPOINT FASE 2: Dijkstra (Solo Distancia)
# ===================================================================
SQL_DIJKSTRA_DISTANCIA = """
    SELECT rt.cost, ST_AsGeoJSON(v.geom) AS geom_json
    FROM pgr_dijkstra(
        'SELECT id, source, target, cost, reverse_cost FROM via_arista',
        %s, %s, directed := false
    ) AS rt
    JOIN via_arista v ON rt.edge = v.id
    ORDER BY rt.seq;
"""
@app.get("/route-fase2-dijkstra-distancia")
def get_route_distancia(
    src: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    dst: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$")
):
    t_start = time.time()
    try:
        src_lat, src_lon = map(float, src.split(','))
        dst_lat, dst_lon = map(float, dst.split(','))
    except ValueError:
        raise HTTPException(status_code=400, detail="Parámetros 'src' y 'dst' deben ser 'lat,lon'.")
    try:
        with get_db_conn() as conn:
            source_node, _, _ = find_nearest_node(conn, src_lon, src_lat)
            target_node, _, _ = find_nearest_node(conn, dst_lon, dst_lat)
            if source_node is None or target_node is None:
                raise HTTPException(status_code=422, detail="No se pudo encontrar un nodo de red cercano (fuera del área).")
            if source_node == target_node:
                return {"type": "FeatureCollection", "features": [], "properties": {"total_cost_meters": 0, "compute_time_ms": 0}}
            with conn.cursor() as cur:
                cur.execute(SQL_DIJKSTRA_DISTANCIA, (source_node, target_node))
                rows = cur.fetchall()
                route_geoms = [row[1] for row in rows if row[1]]
                total_cost = sum(row[0] for row in rows)
                t_end = time.time()
                time_ms = (t_end - t_start) * 1000
                geojson_response = format_route_as_geojson(route_geoms, total_cost, time_ms)
                geojson_response["properties"]["route_type"] = "Dijkstra (Distancia)"
                return JSONResponse(content=geojson_response)
    except Exception as e:
        print(f"Error en consulta Dijkstra (distancia): {e}", file=sys.stderr)
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Error al calcular la ruta: {e}")

# ===================================================================
# 📍 ENDPOINT FASE 3: Dijkstra (con Variables de Amenaza)
# ===================================================================
SQL_DIJKSTRA_VARS_TEMPLATE = """
    SELECT rt.cost, ST_AsGeoJSON(v.geom) AS geom_json
    FROM pgr_dijkstra(
        -- 1. La Consulta de Costo Dinámico
        $SQL$
        WITH
        threats_at_hour AS (
          SELECT
            {hora} AS hora,
            COALESCE((SELECT temp_c FROM amenaza_calor_grid WHERE hora = {hora} LIMIT 1), 15.0) AS temp,
            COALESCE((SELECT uvi FROM amenaza_uv_grid WHERE hora = {hora} LIMIT 1), 0.0) AS uv
        ),
        arista_shadow AS (
          SELECT
            v.id,
            EXISTS (
              SELECT 1 FROM sombra_poligono s
              WHERE s.hora = {hora}
              AND ST_Intersects(s.geom, ST_PointOnSurface(v.geom))
            ) AS in_sombra
          FROM via_arista v
        )
        SELECT
          v.id, v.source, v.target,
          ( v.length_m
            + v.length_m * (GREATEST(0.0, (SELECT temp FROM threats_at_hour) - 20.0) * 0.025)
            + v.length_m * ((SELECT uv FROM threats_at_hour) * 0.10)
          ) * CASE WHEN shadow.in_sombra THEN (1.0 - 0.8) ELSE 1.0 END AS cost,
          ( v.length_m
            + v.length_m * (GREATEST(0.0, (SELECT temp FROM threats_at_hour) - 20.0) * 0.025)
            + v.length_m * ((SELECT uv FROM threats_at_hour) * 0.10)
          ) * CASE WHEN shadow.in_sombra THEN (1.0 - 0.8) ELSE 1.0 END AS reverse_cost
        FROM via_arista v
        JOIN threats_at_hour ON true
        LEFT JOIN arista_shadow shadow ON v.id = shadow.id
        $SQL$,
        %s, %s, directed := false
    ) AS rt
    JOIN via_arista v ON rt.edge = v.id
    ORDER BY rt.seq;
"""
@app.get("/route-fase3-dijkstra-vars")
def get_route_variables(
    src: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    dst: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    hora: int | None = Query(None)
):
    t_start = time.time()
    hora_actual = hora if (hora is not None and 0 <= hora <= 23) else datetime.now().hour
    try:
        src_lat, src_lon = map(float, src.split(','))
        dst_lat, dst_lon = map(float, dst.split(','))
    except ValueError:
        raise HTTPException(status_code=400, detail="Parámetros 'src' y 'dst' deben ser 'lat,lon'.")
    try:
        with get_db_conn() as conn:
            source_node, _, _ = find_nearest_node(conn, src_lon, src_lat)
            target_node, _, _ = find_nearest_node(conn, dst_lon, dst_lat)
            if source_node is None or target_node is None:
                raise HTTPException(status_code=422, detail="No se pudo encontrar un nodo de red cercano (fuera del área).")
            if source_node == target_node:
                return {"type": "FeatureCollection", "features": [], "properties": {"total_cost_meters": 0, "compute_time_ms": 0}}
            
            with conn.cursor() as cur:
                formatted_sql = sql.SQL(SQL_DIJKSTRA_VARS_TEMPLATE).format(
                    hora=sql.Literal(hora_actual)
                )
                cur.execute(formatted_sql, (source_node, target_node))
                rows = cur.fetchall()
                
                route_geoms = [row[1] for row in rows if row[1]]
                total_cost = sum(row[0] for row in rows)
                t_end = time.time()
                time_ms = (t_end - t_start) * 1000
                geojson_response = format_route_as_geojson(route_geoms, total_cost, time_ms)
                geojson_response["properties"]["route_type"] = f"Dijkstra (Amenazas Hora {hora_actual})"
                geojson_response["properties"]["hora_calculada"] = hora_actual
                return JSONResponse(content=geojson_response)
    except Exception as e:
        print(f"Error en consulta Dijkstra (variables): {e}", file=sys.stderr)
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Error al calcular la ruta: {e}")

# ===================================================================
# 📍 ENDPOINT FASE 3: A* (A-Star)
# ===================================================================
SQL_ASTAR_VARS_TEMPLATE = """
    SELECT rt.cost, ST_AsGeoJSON(v.geom) AS geom_json
    FROM pgr_aStar(
        -- 1. La Consulta de Costo Dinámico
        ($SQL$
        WITH
        threats_at_hour AS (
          SELECT
            {hora} AS hora,
            COALESCE((SELECT temp_c FROM amenaza_calor_grid WHERE hora = {hora} LIMIT 1), 15.0) AS temp,
            COALESCE((SELECT uvi FROM amenaza_uv_grid WHERE hora = {hora} LIMIT 1), 0.0) AS uv
        ),
        arista_shadow AS (
          SELECT
            v.id,
            EXISTS (
              SELECT 1 FROM sombra_poligono s
              WHERE s.hora = {hora}
              AND ST_Intersects(s.geom, ST_PointOnSurface(v.geom))
            ) AS in_sombra
          FROM via_arista v
        ),
        nodes AS (
            SELECT id, ST_X(geom) as x, ST_Y(geom) as y FROM via_arista_vertices_pgr
        )
        SELECT
          v.id, v.source, v.target,
          ( v.length_m
            + v.length_m * (GREATEST(0.0, (SELECT temp FROM threats_at_hour) - 20.0) * 0.025)
            + v.length_m * ((SELECT uv FROM threats_at_hour) * 0.10)
          ) * CASE WHEN shadow.in_sombra THEN (1.0 - 0.8) ELSE 1.0 END AS cost,
          ( v.length_m
            + v.length_m * (GREATEST(0.0, (SELECT temp FROM threats_at_hour) - 20.0) * 0.025)
            + v.length_m * ((SELECT uv FROM threats_at_hour) * 0.10)
          ) * CASE WHEN shadow.in_sombra THEN (1.0 - 0.8) ELSE 1.0 END AS reverse_cost,
          n_source.x AS x1, n_source.y AS y1,
          n_target.x AS x2, n_target.y AS y2
        FROM via_arista v
        JOIN threats_at_hour ON true
        LEFT JOIN arista_shadow shadow ON v.id = shadow.id
        JOIN nodes n_source ON v.source = n_source.id
        JOIN nodes n_target ON v.target = n_target.id
        $SQL$)::TEXT,
        
        -- 2. Parámetros de A*
        %s::BIGINT, %s::BIGINT, -- source_node, target_node
        directed := false,
        
        -- CORRECCIÓN BUG 2: Eliminado 'heuristic := 3'
        -- Esta firma de pgr_aStar (con end_x/end_y) usa la
        -- heurística de distancia por defecto.
        end_x := %s, end_y := %s -- x (float), y (float)
    ) AS rt
    JOIN via_arista v ON rt.edge = v.id
    ORDER BY rt.seq;
"""
@app.get("/route-fase3-astar-vars")
def get_route_astar_variables(
    src: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    dst: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    hora: int | None = Query(None)
):
    t_start = time.time()
    hora_actual = hora if (hora is not None and 0 <= hora <= 23) else datetime.now().hour
    try:
        src_lat, src_lon = map(float, src.split(','))
        dst_lat, dst_lon = map(float, dst.split(','))
    except ValueError:
        raise HTTPException(status_code=400, detail="Parámetros 'src' y 'dst' deben ser 'lat,lon'.")
    try:
        with get_db_conn() as conn:
            source_node, _, _ = find_nearest_node(conn, src_lon, src_lat)
            target_node, target_x, target_y = find_nearest_node(conn, dst_lon, dst_lat)
            
            if source_node is None or target_node is None:
                raise HTTPException(status_code=422, detail="No se pudo encontrar un nodo de red cercano (fuera del área).")
            if source_node == target_node:
                return {"type": "FeatureCollection", "features": [], "properties": {"total_cost_meters": 0, "compute_time_ms": 0}}
            
            with conn.cursor() as cur:
                formatted_sql = sql.SQL(SQL_ASTAR_VARS_TEMPLATE).format(
                    hora=sql.Literal(hora_actual)
                )
                
                params = (
                    source_node,
                    target_node,
                    target_x,
                    target_y
                )
                
                cur.execute(formatted_sql, params)
                rows = cur.fetchall()
                
                route_geoms = [row[1] for row in rows if row[1]]
                total_cost = sum(row[0] for row in rows)
                t_end = time.time()
                time_ms = (t_end - t_start) * 1000
                geojson_response = format_route_as_geojson(route_geoms, total_cost, time_ms)
                geojson_response["properties"]["route_type"] = f"A* (Amenazas Hora {hora_actual})"
                geojson_response["properties"]["hora_calculada"] = hora_actual
                return JSONResponse(content=geojson_response)
    except Exception as e:
        print(f"Error en consulta A* (variables): {e}", file=sys.stderr)
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Error al calcular la ruta: {e}")

# --- Endpoints de Salud y Raíz (sin cambios) ---
@app.get("/health")
def health_check():
    return {"status": "OK", "timestamp": datetime.now().isoformat()}
@app.get("/")
def read_root():
    return {
        "message": "API de Ruteo Fase 3",
        "endpoints": {
            "/health": "Estado de la API",
            "/route-fase2-dijkstra-distancia": "Ruta más corta (solo distancia)",
            "/route-fase3-dijkstra-vars": "Ruta óptima (Dijkstra + amenazas)",
            "/route-fase3-astar-vars": "Ruta óptima (A* + amenazas)"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port="8000")
