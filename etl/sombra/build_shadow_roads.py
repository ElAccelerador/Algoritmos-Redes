#!/usr/bin/env python3
import json, math, sys
from pathlib import Path
from datetime import datetime, date, time # <-- MODIFICADO
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
# <-- MODIFICADO: Leemos la fecha base, pero ignoramos la hora hardcodeada
BASE_DT = datetime.strptime(CFG["datetime_local"], "%Y-%m-%d %H:%M:%S")
BASE_DATE = BASE_DT.date()
# <-- MODIFICADO: Definimos el rango de horas a calcular
HORA_INICIO = 8
HORA_FIN = 18 # (No inclusivo, por lo que calcula hasta las 17:00)

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
    return shp_transform(lambda x, y: fwd.transform(x, y), geom)

def proj_inverse(geom, inv: Transformer):
    return shp_transform(lambda x, y: inv.transform(x, y), geom)

def ensure_poly(g):
    if g.geom_type == "Polygon": return [g]
    if g.geom_type == "MultiPolygon": return list(g.geoms)
    return []

def main():
    # Proyecciones
    wgs84 = CRS.from_epsg(4326)
    utm   = CRS.from_epsg(EPSG)
    fwd = Transformer.from_crs(wgs84, utm, always_xy=True)    # lon,lat -> X,Y
    inv = Transformer.from_crs(utm, wgs84, always_xy=True)    # X,Y -> lon,lat

    # Cargar Edificios (una sola vez)
    b = read_fc(B_GJ)
    buildings = []
    for f in b.get("features", []):
        props = f.get("properties") or {}
        h = props.get("height_m")
        if h is None: continue
        try: h = float(h)
        except: continue
        if h <= 0: continue
        geom = f.get("geometry")
        if not geom: continue
        g = shape(geom)
        if g.is_empty: continue
        buildings.append((g, h))
        
    if not buildings:
        print("[ERR] No hay edificios con height_m válido", file=sys.stderr); sys.exit(2)
    
    # Proyectar edificios a UTM (una sola vez)
    b_utm = [(proj_forward(g, fwd), h) for g,h in buildings]
    print(f"[INFO] Edificios cargados: {len(b_utm)}")

    # Cargar Infraestructura (una sola vez)
    roads=[]
    for p in INFRA_FILES:
        if not p.exists(): continue
        j = read_fc(p)
        for f in j.get("features", []):
            g = shape(f.get("geometry"))
            if not g.is_empty and g.geom_type in ("LineString","MultiLineString"):
                roads.append(g)
    if not roads:
        print("[ERR] No hay vías en los GeoJSON de infraestructura", file=sys.stderr); sys.exit(2)
        
    # Proyectar vías a UTM (una sola vez)
    r_utm = [proj_forward(g, fwd) for g in roads]
    print(f"[INFO] Vías cargadas: {len(r_utm)}")

    obs = Observer(latitude=LAT, longitude=LON)
    
    # <-- MODIFICADO: Listas para acumular features de TODAS las horas
    all_shadow_polys_utm = []
    all_shaded_lines_utm = []

    # <-- MODIFICADO: Bucle principal por hora
    print(f"[INFO] Calculando sombras para el {BASE_DATE} desde {HORA_INICIO}:00 hasta {HORA_FIN-1}:00...")
    
    for hora_actual in range(HORA_INICIO, HORA_FIN):
        DT = datetime.combine(BASE_DATE, time(hour=hora_actual))
        print(f"[INFO] ... procesando {hora_actual}:00")

        elev = sun_elevation(obs, DT)
        azim = sun_azimuth(obs, DT) % 360.0
        
        if elev <= 0:
            print(f"[WARN] {hora_actual}:00 Sol bajo o de noche (elev={elev:.1f}°). Saltando hora.")
            continue
            
        alt_rad = math.radians(max(elev, 0.1)) # Evita div por cero
        az_move_rad = math.radians((azim + 180.0) % 360.0)
        tan_alt = math.tan(alt_rad)
        sinA, cosA = math.sin(az_move_rad), math.cos(az_move_rad)

        shadows_this_hour = []
        for poly_utm, h in b_utm:
            d = h / tan_alt
            dx = d * sinA
            dy = d * cosA
            
            for poly in ensure_poly(poly_utm):
                moved = translate(poly, xoff=dx, yoff=dy)
                hull = poly.union(moved).convex_hull
                shadows_this_hour.append(hull)

        if not shadows_this_hour:
            print(f"[WARN] {hora_actual}:00 no se generaron sombras.")
            continue

        shadow_union_this_hour = unary_union(shadows_this_hour)
        
        # Guardamos el polígono de sombra de esta hora CON su propiedad de hora
        all_shadow_polys_utm.append((shadow_union_this_hour, hora_actual))

        # Intersecar con vías
        for ln in r_utm:
            try:
                if ln.intersects(shadow_union_this_hour):
                    inter = ln.intersection(shadow_union_this_hour)
                    if inter.is_empty: continue
                    inter = inter.buffer(0).simplify(0.05) or inter
                    # Guardamos la vía sombreada CON su propiedad de hora
                    all_shaded_lines_utm.append((inter, hora_actual))
            except Exception:
                pass
    
    # --- FIN DEL BUCLE ---
    print(f"[INFO] Cálculo de horas finalizado. Proyectando a WGS84 y guardando...")

    # Salidas
    # 1) Polígonos de sombra (FeatureCollection con todas las horas)
    feats_polys=[]
    for g_utm, hora in all_shadow_polys_utm:
        g_wgs = proj_inverse(g_utm, inv)
        props = {"hora": hora} # <-- LA NUEVA PROPIEDAD
        if g_wgs.geom_type == "Polygon":
            feats_polys.append({"type":"Feature","geometry":mapping(g_wgs),"properties":props})
        elif g_wgs.geom_type == "MultiPolygon":
            feats_polys += [{"type":"Feature","geometry":mapping(g),"properties":props} for g in g_wgs.geoms]
            
    OUT_SHADOWS.write_text(json.dumps({"type":"FeatureCollection","features":feats_polys}, ensure_ascii=False))

    # 2) Vías sombreadas (FeatureCollection con todas las horas)
    feats_lines=[]
    for g_utm, hora in all_shaded_lines_utm:
        g_wgs = proj_inverse(g_utm, inv)
        props = {"shaded":True, "hora": hora} # <-- LA NUEVA PROPIEDAD
        if g_wgs.is_empty: continue
        if g_wgs.geom_type == "LineString":
            feats_lines.append({"type":"Feature","geometry":mapping(g_wgs),"properties":props})
        elif g_wgs.geom_type == "MultiLineString":
            feats_lines += [{"type":"Feature","geometry":mapping(p),"properties":props} for p in g_wgs.geoms]
            
    OUT_SHADED.write_text(json.dumps({"type":"FeatureCollection","features":feats_lines}, ensure_ascii=False))

    print(f"OK sombras: {len(feats_polys)} polígonos | vías sombreadas: {len(feats_lines)} (total acumulado de todas las horas)")

if __name__ == "__main__":
    main()
