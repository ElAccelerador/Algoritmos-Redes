#!/usr/bin/env python3
import json, time, math
from pathlib import Path
import requests, yaml
from datetime import datetime

CFG = yaml.safe_load(Path("etl/amenazas/temp_grid_config.yaml").read_text())
S,W,N,E = CFG["bbox"]
# <-- MODIFICADO: Ya no leemos NY, NX. Usaremos 1 solo polígono.
API = CFG["api_base"]
Q = "hourly=temperature_2m&forecast_days=1" 
SLEEP = float(CFG.get("sleep_s", 0.15)) # (Aunque ahora solo se usa 1 vez)

# <-- MODIFICADO: Eliminadas las funciones linspace() y mk_grid()

def fetch_temp_hourly(lat, lon):
    url = f"{API}?latitude={lat:.6f}&longitude={lon:.6f}&{Q}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    j = r.json()
    
    hourly_data = j.get("hourly", {})
    times = hourly_data.get("time", [])
    temps = hourly_data.get("temperature_2m", [])
    
    results = []
    if times and temps and len(times) == len(temps):
        for iso_time, temp_val in zip(times, temps):
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

    # <-- MODIFICADO: Definimos un solo polígono para todo el BBOX
    full_bbox_poly = [[W,N],[E,N],[E,S],[W,S],[W,N]]
    
    # <-- MODIFICADO: Calculamos un solo punto central para la consulta
    lat_center = (S + N) / 2.0
    lon_center = (W + E) / 2.0

    try:
        # <-- MODIFICADO: Hacemos UNA sola llamada a la API
        hourly_results, _gen_time = fetch_temp_hourly(lat_center, lon_center)
    except Exception as e:
        print(f"[ERROR] Falló el fetch de Open-Meteo: {e}")
        hourly_results = []
        sys.exit(1) # Salimos si la API falla

    # <-- MODIFICADO: Bucle para crear un feature POR HORA, usando el mismo polígono
    for data_point in hourly_results:
        props = {
            "temp_c": data_point["temp"],
            "hora": data_point["hora"], # La propiedad clave
            "row": 0, # Valor simbólico
            "col": 0, # Valor simbólico
            "centroid": {"lon": lon_center, "lat": lat_center}
        }
        feats.append({
            "type":"Feature",
            # Usamos el polígono del BBOX completo
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
    # <-- MODIFICADO: El número de features ahora es 24 (o las horas que devuelva la API)
    print(f"OK json/amenaza_temp_grid.geojson features={len(feats)} (1 por hora) time={meta_time}")

if __name__=="__main__":
    main()
