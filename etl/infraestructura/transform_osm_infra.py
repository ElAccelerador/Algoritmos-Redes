#!/usr/bin/env python3
import json
from pathlib import Path
from etl.utils.geo import haversine_m

SRC = Path("data/osm_providencia_highways.json")
OUT = Path("json/infraestructura.geojson")

def main():
    data = json.loads(SRC.read_text())
    feats = []
    eid = 1
    for w in data.get("elements", []):
        if w.get("type") != "way": continue
        g = w.get("geometry", [])
        if len(g) < 2: continue
        coords_latlon = [(n["lat"], n["lon"]) for n in g]
        length = sum(haversine_m(coords_latlon[i], coords_latlon[i+1]) for i in range(len(coords_latlon)-1))
        props = {
            "id": eid,
            "osm_id": w.get("id"),
            "highway": w.get("tags", {}).get("highway"),
            "oneway": w.get("tags", {}).get("oneway") in ("yes","1","true"),
            "length_m": round(length,2)
        }
        gj_coords = [[c[1], c[0]] for c in coords_latlon]
        feats.append({"type":"Feature","geometry":{"type":"LineString","coordinates":gj_coords},"properties":props})
        eid += 1
    fc = {"type":"FeatureCollection","name":"infraestructura","crs":{"type":"name","properties":{"name":"EPSG:4326"}}, "features":feats}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fc, ensure_ascii=False))
    print(f"OK:{OUT}")

if __name__ == "__main__":
    main()
