#!/usr/bin/env python3
import json, math, sys
from pathlib import Path
from datetime import datetime
import yaml
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, LineString, MultiLineString
from shapely.affinity import translate
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer, CRS
from astral import Observer
from astral.sun import azimuth as sun_azimuth, elevation as sun_elevation

# Config
CFG = yaml.safe_load(Path("etl/sombra/sombra_config.yaml").read_text())
LAT = float(CFG["center_lat"])
LON = float(CFG["center_lon"])
DT  = datetime.strptime(CFG["datetime_local"], "%Y-%m-%d %H:%M:%S")  # hora local dada
EPSG = int(CFG["target_epsg"])
B_GJ = Path(CFG["buildings_geojson"])
INFRA_FILES = [Path(p) for p in CFG["infra_files"]]
OUT_SHADOWS = Path(CFG["shadows_geojson"])
OUT_SHADED  = Path(CFG["shaded_roads_geojson"])

def read_fc(p: Path):
    if not p.exists():
        print(f"[ERR] Falta archivo: {p}", file=sys.stderr); sys.exit(2)
    try:
        return json.loads(p.read_text())
    except Exception as e:
        print(f"[ERR] JSON inválido: {p}: {e}", file=sys.stderr); sys.exit(2)

def proj_forward(geom, fwd: Transformer):
    # (lon,lat) -> (X,Y)
    return shp_transform(lambda x, y: fwd.transform(x, y), geom)

def proj_inverse(geom, inv: Transformer):
    # (X,Y) -> (lon,lat)
    return shp_transform(lambda x, y: inv.transform(x, y), geom)

def ensure_poly(g):
    if g.geom_type == "Polygon": return [g]
    if g.geom_type == "MultiPolygon": return list(g.geoms)
    return []

def main():
    # Proyecciones
    wgs84 = CRS.from_epsg(4326)
    utm   = CRS.from_epsg(EPSG)
    fwd = Transformer.from_crs(wgs84, utm, always_xy=True)   # lon,lat -> X,Y
    inv = Transformer.from_crs(utm, wgs84, always_xy=True)   # X,Y -> lon,lat

    # Sol a las 12:00 local (según config)
    obs = Observer(latitude=LAT, longitude=LON)
    elev = sun_elevation(obs, DT)           # grados sobre el horizonte
    azim = sun_azimuth(obs, DT) % 360.0     # grados desde el Norte, sentido horario
    if elev <= 0:
        print(f"[WARN] Altitud solar <= 0 ({elev:.2f}°). Sombras muy largas o sin sol.", file=sys.stderr)
    alt_rad = math.radians(max(elev, 1.0))  # evita tangente infinita
    az_move_rad = math.radians((azim + 180.0) % 360.0)  # vector opuesto al sol

    # Edificios con height_m
    b = read_fc(B_GJ)
    buildings = []
    for f in b.get("features", []):
        props = f.get("properties") or {}
        h = props.get("height_m")
        if h is None: 
            continue
        try:
            h = float(h)
        except:
            continue
        if h <= 0:
            continue
        geom = f.get("geometry")
        if not geom:
            continue
        g = shape(geom)
        if g.is_empty:
            continue
        buildings.append((g, h))
    if not buildings:
        print("[ERR] No hay edificios con height_m válido en metadata_edificios.geojson", file=sys.stderr); sys.exit(2)

    # Infraestructura (líneas)
    roads=[]
    for p in INFRA_FILES:
        if not p.exists():
            print(f"[INFO] Infra ausente (se ignora): {p}", file=sys.stderr)
            continue
        j = read_fc(p)
        for f in j.get("features", []):
            geom = f.get("geometry")
            if not geom: continue
            g = shape(geom)
            if g.is_empty: continue
            if g.geom_type in ("LineString","MultiLineString"):
                roads.append(g)
    if not roads:
        print("[ERR] No hay vías en los GeoJSON de infraestructura", file=sys.stderr); sys.exit(2)

    # A UTM
    b_utm = [(proj_forward(g, fwd), h) for g,h in buildings]
    r_utm = [proj_forward(g, fwd) for g in roads]

    # Sombras (trasladar footprint una distancia d = h / tan(alt), contra el sol)
    tan_alt = math.tan(alt_rad)
    sinA, cosA = math.sin(az_move_rad), math.cos(az_move_rad)

    shadows=[]
    for poly_wgs, h in b_utm:
        for poly in ensure_poly(poly_wgs):
            d  = h / tan_alt
            dx = d * sinA
            dy = d * cosA
            moved = translate(poly, xoff=dx, yoff=dy)
            hull  = poly.union(moved).convex_hull
            shadows.append(hull)

    if not shadows:
        print("[ERR] No se generaron sombras", file=sys.stderr); sys.exit(2)

    shadow_union = unary_union(shadows)

    # Intersecar con vías
    shaded=[]
    for ln in r_utm:
        try:
            if ln.intersects(shadow_union):
                inter = ln.intersection(shadow_union)
                if inter.is_empty:
                    continue
                # Simplificación ligera para aligerar el GeoJSON
                inter = inter.buffer(0).simplify(0.05) or inter
                shaded.append(inter)
        except Exception:
            pass

    # Salidas
    # 1) Polígonos de sombra
    su_wgs = proj_inverse(shadow_union, inv)
    feats_polys=[]
    if su_wgs.geom_type == "Polygon":
        feats_polys=[{"type":"Feature","geometry":mapping(su_wgs),"properties":{}}]
    elif su_wgs.geom_type == "MultiPolygon":
        feats_polys=[{"type":"Feature","geometry":mapping(g),"properties":{}} for g in su_wgs.geoms]
    OUT_SHADOWS.write_text(json.dumps({"type":"FeatureCollection","features":feats_polys}, ensure_ascii=False))

    # 2) Vías sombreadas (líneas)
    shaded_wgs=[proj_inverse(g, inv) for g in shaded]
    feats_lines=[]
    for g in shaded_wgs:
        if g.is_empty: continue
        if g.geom_type == "LineString":
            feats_lines.append({"type":"Feature","geometry":mapping(g),"properties":{"shaded":True}})
        elif g.geom_type == "MultiLineString":
            feats_lines += [{"type":"Feature","geometry":mapping(p),"properties":{"shaded":True}} for p in g.geoms]
    OUT_SHADED.write_text(json.dumps({"type":"FeatureCollection","features":feats_lines}, ensure_ascii=False))

    print(f"OK sombras: {len(feats_polys)} polígonos | vías sombreadas: {len(feats_lines)}")
    print(f"Sol: elev={elev:.1f}°  azim={azim:.1f}°")

if __name__ == "__main__":
    main()
