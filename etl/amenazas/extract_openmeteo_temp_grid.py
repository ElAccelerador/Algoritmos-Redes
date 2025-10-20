#!/usr/bin/env python3
import json, time, math
from pathlib import Path
import requests, yaml

CFG = yaml.safe_load(Path("etl/amenazas/temp_grid_config.yaml").read_text())
S,W,N,E = CFG["bbox"]
NY, NX = int(CFG["cells_y"]), int(CFG["cells_x"])
API = CFG["api_base"]; Q = CFG["query"]
SLEEP = float(CFG.get("sleep_s", 0.15))

def linspace(a,b,n):
    if n==1: return [a]
    step=(b-a)/n
    return [a+i*step for i in range(n+1)]

def mk_grid(bbox, ny, nx):
    S,W,N,E = bbox
    ys = linspace(N, S, ny)   # de norte a sur
    xs = linspace(W, E, nx)   # de oeste a este
    cells=[]
    for iy in range(ny):
        for ix in range(nx):
            y1, y0 = ys[iy], ys[iy+1]
            x0, x1 = xs[ix], xs[ix+1]
            poly = [[x0,y1],[x1,y1],[x1,y0],[x0,y0],[x0,y1]]
            cy = (y0+y1)/2.0
            cx = (x0+x1)/2.0
            cells.append({"poly":poly, "centroid":[cx,cy], "row":iy, "col":ix})
    return cells

def fetch_temp(lat, lon):
    # Open-Meteo: temperatura actual (°C) en current_weather.temperature
    url = f"{API}?latitude={lat:.6f}&longitude={lon:.6f}&{Q}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    j = r.json()
    cw = j.get("current_weather") or {}
    t  = cw.get("temperature")
    tm = cw.get("time")
    return t, tm, j

def main():
    Path("json").mkdir(parents=True, exist_ok=True)
    cells = mk_grid((S,W,N,E), NY, NX)
    feats=[]
    meta_time=None
    for c in cells:
        lat = c["centroid"][1]
        lon = c["centroid"][0]
        try:
            t, tm, raw = fetch_temp(lat, lon)
            if meta_time is None: meta_time = tm
        except Exception as e:
            t, raw = None, {"error": str(e)}
        props = {
            "temp_c": t,
            "row": c["row"],
            "col": c["col"],
            "centroid": {"lon": lon, "lat": lat}
        }
        feats.append({
            "type":"Feature",
            "geometry":{"type":"Polygon","coordinates":[c["poly"]]},
            "properties": props
        })
        time.sleep(SLEEP)

    gj = {
        "type":"FeatureCollection",
        "features":feats,
        "crs":{"type":"name","properties":{"name":"EPSG:4326"}},
        "properties":{"source":"open-meteo","time":meta_time}
    }
    Path("json/amenaza_temp_grid.geojson").write_text(json.dumps(gj, ensure_ascii=False))
    print(f"OK json/amenaza_temp_grid.geojson cells={len(feats)} time={meta_time}")

if __name__=="__main__":
    main()
