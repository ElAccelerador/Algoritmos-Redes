#!/usr/bin/env python3
import json, time, sys
from pathlib import Path
import requests, yaml
from datetime import datetime, timezone

CFG = yaml.safe_load(Path("etl/amenazas/uv_grid_config.yaml").read_text())
S,W,N,E = CFG["bbox"]
API     = CFG["api_base"]
KEY     = CFG["api_key"]
# MODIFICADO: Nos aseguramos de NO excluir 'hourly'
EXC     = "minutely,daily,alerts" 
UNITS   = CFG.get("units","metric")
SLEEP   = float(CFG.get("sleep_s",0.2))

# --- RANGO DE HORAS A PROCESAR (06:00 a 20:00) ---
HORA_MIN = 6
HORA_MAX = 20
# ------------------------------------------------

def fetch_uv_hourly(lat, lon):
    params = {
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "exclude": EXC,
        "appid": KEY,
        "units": UNITS
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    
    # MODIFICADO: Tomar solo las primeras 24 horas
    hourly_data = j.get("hourly", [])[:24]
    results = []
    
    for entry in hourly_data:
        uvi = entry.get("uvi")
        ts = entry.get("dt") # Timestamp de Unix
        if uvi is None or ts is None:
            continue
            
        try:
            dt_obj = datetime.fromtimestamp(ts, timezone.utc) 
            hour = dt_obj.hour 
            results.append({"hora": hour, "uvi": uvi, "timestamp": ts})
        except Exception:
            continue
            
    return results, j.get("current", {}).get("dt")

def main():
    Path("json").mkdir(parents=True, exist_ok=True)
    feats=[]
    meta_time_unix = None

    full_bbox_poly = [[W,N],[E,N],[E,S],[W,S],[W,N]]
    lat_center = (S + N) / 2.0
    lon_center = (W + E) / 2.0

    try:
        hourly_results, current_ts = fetch_uv_hourly(lat_center, lon_center)
        if meta_time_unix is None: meta_time_unix = current_ts
    except Exception as e:
        print(f"[ERROR] Falló el fetch de OpenWeather: {e}")
        hourly_results = []
        sys.exit(1)

    for data_point in hourly_results:
        # --- MODIFICADO: FILTRO DE HORA ---
        hora = data_point["hora"]
        if not (HORA_MIN <= hora <= HORA_MAX):
            continue # Saltar esta hora (es de noche)
        # ----------------------------------

        props = {
            # MODIFICADO: El script original guardaba "uv_index", 
            # pero la BD y el server.py esperan "uvi".
            "uvi": data_point["uvi"], 
            "hora": data_point["hora"],
            "row": 0, "col": 0,
            "centroid": {"lon": lon_center, "lat": lat_center},
            "timestamp": data_point["timestamp"]
        }
        feats.append({
            "type":"Feature",
            "geometry":{"type":"Polygon","coordinates":[full_bbox_poly]},
            "properties": props
        })
            
    gj = {
        "type":"FeatureCollection",
        "features":feats,
        "crs":{"type":"name","properties":{"name":"EPSG:4326"}},
        "properties":{"source":"openweather","generated_time_unix":meta_time_unix}
    }
    Path("json/amenaza_uv_grid.geojson").write_text(json.dumps(gj, ensure_ascii=False))
    print(f"OK json/amenaza_uv_grid.geojson features={len(feats)} (1 por hora diurna) time_unix={meta_time_unix}")

if __name__=="__main__":
    main()
