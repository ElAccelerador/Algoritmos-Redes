#!/usr/bin/env python3
import json, time
from pathlib import Path
import requests, yaml

CFG = yaml.safe_load(Path("etl/amenazas/uv_grid_config.yaml").read_text())
S,W,N,E = CFG["bbox"]
NY, NX  = int(CFG["cells_y"]), int(CFG["cells_x"])
API     = CFG["api_base"]
KEY     = CFG["api_key"]
EXC     = CFG.get("exclude","minutely,hourly,daily,alerts")
UNITS   = CFG.get("units","metric")
SLEEP   = float(CFG.get("sleep_s",0.2))

def linspace(a,b,n):
    if n==1: return [a]
    step = (b-a)/n
    return [a+i*step for i in range(n+1)]

def make_grid(bbox, ny, nx):
    S,W,N,E = bbox
    ys = linspace(N,S,ny)  # N→S
    xs = linspace(W,E,nx)  # W→E
    cells=[]
    for iy in range(ny):
        for ix in range(nx):
            yN, yS = ys[iy], ys[iy+1]
            xW, xE = xs[ix], xs[ix+1]
            poly = [[xW,yN],[xE,yN],[xE,yS],[xW,yS],[xW,yN]]
            cy = (yN+yS)/2.0; cx = (xW+xE)/2.0
            cells.append({"poly":poly, "centroid":[cx,cy], "row":iy, "col":ix})
    return cells

def fetch_uv(lat, lon):
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
    uvi = (j.get("current") or {}).get("uvi")
    t   = (j.get("current") or {}).get("dt")
    return uvi, t, j

def main():
    Path("json").mkdir(parents=True, exist_ok=True)
    feats=[]
    cells = make_grid((S,W,N,E), NY, NX)
    meta_time=None
    for c in cells:
        lat = c["centroid"][1]; lon = c["centroid"][0]
        try:
            uvi, ts, _raw = fetch_uv(lat, lon)
            if meta_time is None: meta_time = ts
        except Exception as e:
            uvi, ts = None, None
        props = {
            "uv_index": uvi,
            "row": c["row"], "col": c["col"],
            "centroid": {"lon": lon, "lat": lat},
            "timestamp": ts
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
        "properties":{"source":"openweather","time_unix":meta_time}
    }
    Path("json/amenaza_uv_grid.geojson").write_text(json.dumps(gj, ensure_ascii=False))
    print(f"OK json/amenaza_uv_grid.geojson cells={len(feats)} time_unix={meta_time}")

if __name__=="__main__":
    main()
