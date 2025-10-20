from fastapi import FastAPI
from fastapi.responses import JSONResponse
import psycopg2, json, os

app = FastAPI()
conn = psycopg2.connect(host=os.getenv("DB_HOST","db"),
                        dbname=os.getenv("DB_NAME","gis"),
                        user=os.getenv("DB_USER","postgres"),
                        password=os.getenv("DB_PASS","postgres"))

@app.get("/health")
def health():
    with conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        return {"ok": True}

@app.get("/route")
def route(src: str, dst: str):
    # src/dst = "lat,lon"
    slat,slon = map(float, src.split(','))
    dlat,dlon = map(float, dst.split(','))
    with conn, conn.cursor() as cur:
        cur.execute("""
        WITH s AS (
          SELECT id FROM via_nodo ORDER BY geom <-> ST_SetSRID(ST_Point(%s,%s),4326) LIMIT 1
        ), d AS (
          SELECT id FROM via_nodo ORDER BY geom <-> ST_SetSRID(ST_Point(%s,%s),4326) LIMIT 1
        )
        SELECT ST_AsGeoJSON(ST_LineMerge(ST_Union(geom)))
        FROM via_arista WHERE id IN (
          SELECT edge FROM pgr_dijkstra(
            'SELECT id, source, target, length_m AS cost FROM via_arista',
            (SELECT id FROM s), (SELECT id FROM d), directed := false
          )
        );
        """, (slon,slat, dlon,dlat))
        row = cur.fetchone()
    geom = json.loads(row[0]) if row and row[0] else None
    fc = {"type":"FeatureCollection","features":[{"type":"Feature","geometry":geom,"properties":{"algo":"pgr_dijkstra"}}]}
    return JSONResponse(fc)
