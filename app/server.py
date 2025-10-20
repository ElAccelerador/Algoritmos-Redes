from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware  # <— NUEVO
import os, time, json
import psycopg2

DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("DB_NAME", "gis")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

def db_conn(retries=30, delay=1.0):
    last_err = None
    for _ in range(retries):
        try:
            return psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        except Exception as e:
            last_err = e
            time.sleep(delay)
    raise last_err

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -------------

@app.get("/health")
def health():
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        return {"ok": True}

@app.get("/route")
def route(src: str, dst: str):
    slat, slon = map(float, src.split(","))
    dlat, dlon = map(float, dst.split(","))
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("""
        WITH s AS (
          SELECT id FROM via_nodo
          ORDER BY geom <-> ST_SetSRID(ST_Point(%s,%s),4326) LIMIT 1
        ), d AS (
          SELECT id FROM via_nodo
          ORDER BY geom <-> ST_SetSRID(ST_Point(%s,%s),4326) LIMIT 1
        )
        SELECT ST_AsGeoJSON(ST_LineMerge(ST_Union(geom)))
        FROM via_arista WHERE id IN (
          SELECT edge FROM pgr_dijkstra(
            'SELECT id, source, target, length_m AS cost FROM via_arista',
            (SELECT id FROM s), (SELECT id FROM d), directed := false
          )
        );
        """, (slon, slat, dlon, dlat))
        row = cur.fetchone()
    geom = json.loads(row[0]) if row and row[0] else None
    fc = {"type":"FeatureCollection","features":[{"type":"Feature","geometry":geom,"properties":{"algo":"pgr_dijkstra"}}]}
    return JSONResponse(fc)
