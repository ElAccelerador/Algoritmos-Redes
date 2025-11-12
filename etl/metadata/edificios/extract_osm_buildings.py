#!/usr/bin/env python3
import requests, json, math, sys
from pathlib import Path
import yaml

CFG = yaml.safe_load(Path("etl/metadata/edificios/buildings_config.yaml").read_text())
S,W,N,E    = CFG["bbox"]
URL        = CFG["overpass_url"]
TIMEOUT    = int(CFG.get("timeout_s",180))
LV_H       = float(CFG.get("default_level_h",3.2))
LV_DEF     = int(CFG.get("default_levels",5))

QL = f"""
[out:json][timeout:240];
(
  way["building"]({S},{W},{N},{E});
  relation["building"]({S},{W},{N},{E});
);
out tags geom;
"""

def height_from_tags(tags):
    h = tags.get("height")
    if h:
        try:
            h = str(h).lower().strip()
            if h.endswith("m"): h = h[:-1]
            return float(h)
        except: pass
    lv = tags.get("building:levels")
    if lv:
        try: return float(lv) * LV_H
        except: pass
    return LV_DEF * LV_H

def geom_to_polygon(el):
    g = el.get("geometry")
    if not g: return None
    coords = [[pt["lon"], pt["lat"]] for pt in g]
    if coords[0]!=coords[-1]: coords.append(coords[0])
    return [coords]

def main():
    print("Iniciando descarga de edificios desde Overpass API...")
    try:
        r = requests.post(URL, data={"data":QL}, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        print(f"[ERROR] Timeout: El servidor ({URL}) no respondió en {TIMEOUT} segundos.", file=sys.stderr)
        sys.exit(1)
    
    # --- CORRECCIÓN: Manejo de errores de JSON ---
    try:
        data = r.json()
    except json.JSONDecodeError:
        print(f"[ERROR] Overpass API devolvió una respuesta NO-JSON.", file=sys.stderr)
        print(f"[ERROR] Código de estado: {r.status_code}", file=sys.stderr)
        print(f"[ERROR] Respuesta (primeros 500 caracteres):", file=sys.stderr)
        print(r.text[:500], file=sys.stderr)
        sys.exit(1)
    # --- Fin de la corrección ---

    # Si r.raise_for_status() falla, ahora veremos el error JSON de arriba primero
    r.raise_for_status() 

    feats=[]
    for el in data.get("elements",[]):
        if el.get("type") not in ("way","relation"): continue
        poly = geom_to_polygon(el)
        if not poly: continue
        tags = el.get("tags",{})
        h = height_from_tags(tags)
        feats.append({
            "type":"Feature",
            "geometry":{"type":"Polygon","coordinates":poly},
            "properties":{
                "osm_id": el.get("id"),
                "height_m": round(h,2),
                "levels": tags.get("building:levels"),
                "height_tag": tags.get("height"),
                "building": tags.get("building")
            }
        })
    gj={"type":"FeatureCollection","features":feats,"crs":{"type":"name","properties":{"name":"EPSG:4326"}}}
    Path("json/metadata_edificios.geojson").write_text(json.dumps(gj, ensure_ascii=False))
    print("OK edificios:", len(feats))

if __name__=="__main__":
    main()
