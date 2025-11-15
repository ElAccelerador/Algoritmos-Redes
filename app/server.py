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
            "total_cost": total_cost, # Costo total (no necesariamente metros)
            "compute_time_ms": round(time_ms, 3)
        }
    }

# ===================================================================
# 📍 ENDPOINT FASE 2: Dijkstra (Solo Distancia)
# (Esta función no cambia, sigue siendo nuestra línea base)
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
                return {"type": "FeatureCollection", "features": [], "properties": {"total_cost": 0, "compute_time_ms": 0}}
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
# 📍 LÓGICA DE CÁLCULO DE RUTA (NUEVA)
# ===================================================================

# Esta plantilla SQL calcula el costo para UNA HORA, incluyendo el bono de bebederos
SQL_COSTO_POR_HORA_TEMPLATE = """
    WITH
    threats_at_hour AS (
      SELECT
        {hora} AS hora,
        COALESCE((SELECT temp_c FROM amenaza_calor_grid WHERE hora = {hora} LIMIT 1), 15.0) AS temp,
        COALESCE((SELECT uvi FROM amenaza_uv_grid WHERE hora = {hora} LIMIT 1), 0.0) AS uv
    ),
    arista_bonos AS (
      SELECT
        v.id,
        -- Bono Sombra: 1 si está en sombra, 0 si no
        EXISTS (
          SELECT 1 FROM sombra_poligono s
          WHERE s.hora = {hora}
          AND ST_Intersects(s.geom, ST_PointOnSurface(v.geom))
        ) AS in_sombra,
        -- Bono Bebedero: 1 si está cerca, 0 si no
        EXISTS (
          SELECT 1 FROM bebedero b
          WHERE ST_DWithin(v.geom, b.geom, 0.00045) -- ~50 metros
        ) AS cerca_bebedero
      FROM via_arista v
    )
    SELECT
      v.id, v.source, v.target,
      -- Cálculo de Costo Final
      ( v.length_m
        -- Penalidad Calor: +2.5%% por cada grado > 20°C
        * (1 + (GREATEST(0.0, ta.temp - 20.0) * 0.025))
        -- Penalidad UV: +10%% por cada 1 punto de UV
        * (1 + (ta.uv * 0.10))
      )
      -- Bono Sombra: Descuento de 80%%
      * (CASE WHEN ab.in_sombra THEN 0.2 ELSE 1.0 END)
      -- Bono Bebedero: Descuento de 25%%
      * (CASE WHEN ab.cerca_bebedero THEN 0.75 ELSE 1.0 END)
      AS cost,
      
      -- Costo Inverso (igual para peatones)
      ( v.length_m
        * (1 + (GREATEST(0.0, ta.temp - 20.0) * 0.025))
        * (1 + (ta.uv * 0.10))
      )
      * (CASE WHEN ab.in_sombra THEN 0.2 ELSE 1.0 END)
      * (CASE WHEN ab.cerca_bebedero THEN 0.75 ELSE 1.0 END)
      AS reverse_cost,
      
      -- Coordenadas (solo para A*)
      ST_X(n_source.geom) AS x1, ST_Y(n_source.geom) AS y1,
      ST_X(n_target.geom) AS x2, ST_Y(n_target.geom) AS y2
      
    FROM via_arista v
    JOIN threats_at_hour ta ON true
    LEFT JOIN arista_bonos ab ON v.id = ab.id
    JOIN via_arista_vertices_pgr n_source ON v.source = n_source.id
    JOIN via_arista_vertices_pgr n_target ON v.target = n_target.id
"""

# Plantilla para ejecutar Dijkstra sobre la consulta de costo anterior
SQL_DIJKSTRA_WRAPPER = """
    SELECT rt.cost, ST_AsGeoJSON(v.geom) AS geom_json
    FROM pgr_dijkstra(
        $SQL${sql_costo_por_hora}$SQL$,
        %s, %s, directed := false
    ) AS rt
    JOIN via_arista v ON rt.edge = v.id
    ORDER BY rt.seq;
"""

# Plantilla para ejecutar A* sobre la consulta de costo anterior
SQL_ASTAR_WRAPPER = """
    SELECT rt.cost, ST_AsGeoJSON(v.geom) AS geom_json
    FROM pgr_aStar(
        ($SQL${sql_costo_por_hora}$SQL$)::TEXT,
        %s::BIGINT, -- start_vid
        %s::BIGINT, -- end_vid
        directed := false,
        heuristic := 3,
        factor := 1.0,
        epsilon := 1.0
    ) AS rt
    JOIN via_arista v ON rt.edge = v.id
    ORDER BY rt.seq;
"""

def find_best_route_in_range(
    conn,
    sql_wrapper_template: str, # El SQL de Dijkstra o A*
    source_node: int,
    target_node: int,
    hora_inicio: int,
    hora_fin: int
):
    """
    Itera por cada hora en el rango, calcula la ruta,
    y devuelve la mejor ruta encontrada.
    """
    best_route = {
        "cost": float('inf'),
        "geoms": [],
        "hora": -1,
        "time_ms": 0.0
    }
    
    total_db_time = 0.0

    for hora_actual in range(hora_inicio, hora_fin + 1):
        t_start_db = time.time()
        
        sql_costo_hora = SQL_COSTO_POR_HORA_TEMPLATE.replace("{hora}", str(hora_actual))
        sql_final = sql_wrapper_template.replace("{sql_costo_por_hora}", sql_costo_hora)
        
        
        with conn.cursor() as cur:
            cur.execute(sql_final, (source_node, target_node))
            rows = cur.fetchall()
            
            t_end_db = time.time()
            total_db_time += (t_end_db - t_start_db)
            
            if not rows:
                continue # No se encontró ruta para esta hora

            current_cost = sum((row[0] if row[0] is not None else 0) for row in rows)            
            # 3. Comparar y guardar la mejor
            if current_cost < best_route["cost"]:
                best_route["cost"] = current_cost
                best_route["geoms"] = [row[1] for row in rows if row[1]]
                best_route["hora"] = hora_actual
    
    best_route["time_ms"] = total_db_time * 1000
    
    if best_route["hora"] == -1: # No se encontró ninguna ruta en todo el rango
        return None
        
    return best_route


# ===================================================================
# 📍 ENDPOINT FASE 3: Dijkstra (con RANGO de Variables)
# ===================================================================
@app.get("/route-fase3-dijkstra-vars")
def get_route_variables(
    src: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    dst: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    # --- MODIFICADO: Aceptar rango de horas ---
    hora_inicio: int = Query(..., ge=0, le=23),
    hora_fin: int = Query(..., ge=0, le=23)
):
    if hora_inicio > hora_fin:
        raise HTTPException(status_code=400, detail="La 'hora_inicio' debe ser menor o igual a la 'hora_fin'.")
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
                return {"type": "FeatureCollection", "features": [], "properties": {"total_cost": 0, "compute_time_ms": 0}}
            
            # Llamar a la nueva función de bucle
            best_route = find_best_route_in_range(
                conn, SQL_DIJKSTRA_WRAPPER, source_node, target_node, hora_inicio, hora_fin
            )
            
            if best_route is None:
                geojson_response = format_route_as_geojson([], 0, 0)
            else:
                geojson_response = format_route_as_geojson(best_route["geoms"], best_route["cost"], best_route["time_ms"])
            
            # Añadir la "mejor hora" a la respuesta
            geojson_response["properties"]["route_type"] = f"Dijkstra (Mejor en Rango {hora_inicio}-{hora_fin})"
            geojson_response["properties"]["best_hour"] = best_route["hora"] if best_route else -1
            return JSONResponse(content=geojson_response)
            
    except Exception as e:
        print(f"Error en consulta Dijkstra (variables): {e}", file=sys.stderr)
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Error al calcular la ruta: {e}")

# ===================================================================
# 📍 ENDPOINT FASE 3: A* (con RANGO de Variables)
# ===================================================================
@app.get("/route-fase3-astar-vars")
def get_route_astar_variables(
    src: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    dst: str = Query(..., regex=r"^-?\d+\.?\d*,-?\d+\.?\d*$"),
    # --- MODIFICADO: Aceptar rango de horas ---
    hora_inicio: int = Query(..., ge=0, le=23),
    hora_fin: int = Query(..., ge=0, le=23)
):
    if hora_inicio > hora_fin:
        raise HTTPException(status_code=400, detail="La 'hora_inicio' debe ser menor o igual a la 'hora_fin'.")
    try:
        src_lat, src_lon = map(float, src.split(','))
        dst_lat, dst_lon = map(float, dst.split(','))
    except ValueError:
        raise HTTPException(status_code=400, detail="Parámetros 'src' y 'dst' deben ser 'lat,lon'.")
    try:
        with get_db_conn() as conn:
            source_node, _, _ = find_nearest_node(conn, src_lon, src_lat)
            target_node, _, _ = find_nearest_node(conn, dst_lon, dst_lat) # A* ya no necesita x/y aquí
            
            if source_node is None or target_node is None:
                raise HTTPException(status_code=422, detail="No se pudo encontrar un nodo de red cercano (fuera del área).")
            if source_node == target_node:
                return {"type": "FeatureCollection", "features": [], "properties": {"total_cost": 0, "compute_time_ms": 0}}

            # Llamar a la nueva función de bucle
            best_route = find_best_route_in_range(
                conn, SQL_ASTAR_WRAPPER, source_node, target_node, hora_inicio, hora_fin
            )
            
            if best_route is None:
                geojson_response = format_route_as_geojson([], 0, 0)
            else:
                geojson_response = format_route_as_geojson(best_route["geoms"], best_route["cost"], best_route["time_ms"])

            # Añadir la "mejor hora" a la respuesta
            geojson_response["properties"]["route_type"] = f"A* (Mejor en Rango {hora_inicio}-{hora_fin})"
            geojson_response["properties"]["best_hour"] = best_route["hora"] if best_route else -1
            return JSONResponse(content=geojson_response)
            
    except Exception as e:
        print(f"Error en consulta A* (variables): {e}", file=sys.stderr)
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Error al calcular la ruta: {e}")

# --- Endpoints de Salud y Raíz ---
@app.get("/health")
def health_check():
    return {"status": "OK", "timestamp": datetime.now().isoformat()}
@app.get("/")
def read_root():
    return {
        "message": "API de Ruteo Fase 3 (con Rango de Tiempo y Bebederos)",
        "endpoints": {
            "/health": "Estado de la API",
            "/route-fase2-dijkstra-distancia": "Ruta más corta (solo distancia)",
            "/route-fase3-dijkstra-vars": "Ruta óptima (Dijkstra + amenazas en rango)",
            "/route-fase3-astar-vars": "Ruta óptima (A* + amenazas en rango)"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port="8000")
