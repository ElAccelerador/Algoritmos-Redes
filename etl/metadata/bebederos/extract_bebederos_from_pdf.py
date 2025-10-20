#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import yaml, fitz
from PIL import Image
from skimage.measure import label, regionprops
from skimage.morphology import dilation, square

CFG = yaml.safe_load(Path("etl/metadata/bebederos/bebederos_config.yaml").read_text())
CPTS_PATH = Path("etl/metadata/bebederos/control_points.yaml")
CPTS = yaml.safe_load(CPTS_PATH.read_text()) if CPTS_PATH.exists() else {"control_points":[]}

def pdf_to_image(pdf_path, page_index, dpi):
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_index)
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img

def build_affine(px_ll):
    # x' = a*x + b*y + c ; y' = d*x + e*y + f
    A=[]; B=[]
    for (x,y),(lon,lat) in px_ll:
        A.append([x,y,1,0,0,0]);  B.append(lon)
        A.append([0,0,0,x,y,1]);  B.append(lat)
    A=np.asarray(A,float); B=np.asarray(B,float)
    params, *_ = np.linalg.lstsq(A,B,rcond=None)
    return params.reshape(2,3)  # [[a,b,c],[d,e,f]]

def apply_affine(M, x, y):
    lon = M[0,0]*x + M[0,1]*y + M[0,2]
    lat = M[1,0]*x + M[1,1]*y + M[1,2]
    return float(lon), float(lat)

def mask_by_colors(arr, ranges):
    m = np.zeros(arr.shape[:2], dtype=bool)
    for r in ranges:
        mn=np.array(r["min"],dtype=np.uint8)
        mx=np.array(r["max"],dtype=np.uint8)
        m |= np.all((arr>=mn)&(arr<=mx),axis=2)
    return m

def main():
    # Render PDF
    img = pdf_to_image(CFG["pdf_path"], int(CFG.get("page_index",0)), int(CFG.get("dpi",200)))
    Path("data").mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(img)).save("data/bebederos_render.png")

    # Affín con control points
    pairs=[]
    for p in CPTS.get("control_points",[]):
        (x,y)=p["px"]; (lon,lat)=p["ll"]
        pairs.append(((float(x),float(y)),(float(lon),float(lat))))
    if len(pairs)<3:
        raise SystemExit("ERROR: define >=3 puntos en etl/metadata/bebederos/control_points.yaml")

    M = build_affine(pairs)

    # Detección por color
    arr = np.asarray(img)
    mask = mask_by_colors(arr, CFG["color_ranges"])
    if int(CFG.get("dilate_px",0))>0:
        mask = dilation(mask, square(int(CFG["dilate_px"])))
    lbl = label(mask)

    feats=[]
    for reg in regionprops(lbl):
        if reg.area < int(CFG.get("min_area_px",10)): 
            continue
        y,x = reg.centroid  # (fila,col)
        lon,lat = apply_affine(M, float(x), float(y))
        feats.append({
            "type":"Feature",
            "geometry":{"type":"Point","coordinates":[lon,lat]},
            "properties":{"fuente":"pdf_providencia_affine",
                          "attrs":{"area_px":int(reg.area),"bbox_px":[int(v) for v in reg.bbox]}}
        })

    # Export GeoJSON final y debug de CP
    Path("json").mkdir(parents=True, exist_ok=True)
    Path("json/metadata_bebederos.geojson").write_text(
        json.dumps({"type":"FeatureCollection","features":feats,
                    "crs":{"type":"name","properties":{"name":"EPSG:4326"}}}, ensure_ascii=False)
    )
    dbg=[]
    for (x,y),(lon,lat) in pairs:
        dbg.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},
                    "properties":{"name":f"CP ({int(x)},{int(y)})"}})
    Path("json/metadata_bebederos_controlpoints.geojson").write_text(
        json.dumps({"type":"FeatureCollection","features":dbg,
                    "crs":{"type":"name","properties":{"name":"EPSG:4326"}}}, ensure_ascii=False)
    )
    print(f"OK json/metadata_bebederos.geojson features={len(feats)} CP={len(dbg)}")

if __name__=="__main__":
    main()
