#!/usr/bin/env python3
import json, time, math, sys
from pathlib import Path
import requests, yaml
from datetime import datetime

CFG = yaml.safe_load(Path("etl/amenazas/temp_grid_config.yaml").read_text())
S,W,N,E = CFG["bbox"]
API = CFG["api_base"]
Q = "hourly=temperature_2m&forecast_days=1" # Pide solo 1 día (24h)
SLEEP = float(CFG.get("sleep_s", 0.15))

# --- RANGO DE HORAS A PROCESAR (06:00 a 20:00) ---
HORA_MIN = 6
HORA_MAX = 20
# ------------------------------------------------

def fetch_temp_hourly(lat, lon):
    url = f"{API}?latitude={lat:.6f}&longitude={lon:.6f}&{Q}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    j = r.json()
    
    hourly_data = j.get("hourly", {})
    times = hourly_data.get("time", [])
    temps = hourly_data.get("temperature_2m", [])
    
    results = []
    # MODIFICADO: Tomar solo las primeras 24 horas
    for iso_time, temp_val in zip(times[:24], temps[:24]):
        try:
            hour = datetime.fromisoformat(iso_time).hour
            results.append({"hora": hour, "temp": temp_val})
        except (ValueError, TypeError):
            continue
    return results, j.get("generationtime_ms", 0)

def main():
    Path("json").mkdir(parents=True, exist_ok=True)
    feats=[]
    meta_time=datetime.now().isoformat()

    full_bbox_poly = [[W,N],[E,N],[E,S],[W,S],[W,N]]
    lat_center = (S + N) / 2.0
    lon_center = (W + E) / 2.0

    try:
        hourly_results, _gen_time = fetch_temp_hourly(lat_center, lon_center)
    except Exception as e:
        print(f"[ERROR] Falló el fetch de Open-Meteo: {e}")
        hourly_results = []
        sys.exit(1)

    for data_point in hourly_results:
        # --- MODIFICADO: FILTRO DE HORA ---
        hora = data_point["hora"]
        if not (HORA_MIN <= hora <= HORA_MAX):
            continue # Saltar esta hora (es de noche)
        # ----------------------------------
            
        props = {
            "temp_c": data_point["temp"],
            "hora": hora,
            "row": 0, "col": 0,
            "centroid": {"lon": lon_center, "lat": lat_center}
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
        "properties":{"source":"open-meteo","generated_time":meta_time}
    }
    Path("json/amenaza_temp_grid.geojson").write_text(json.dumps(gj, ensure_ascii=False))
    print(f"OK json/amenaza_temp_grid.geojson features={len(feats)} (1 por hora diurna) time={meta_time}")

if __name__=="__main__":
    main()
