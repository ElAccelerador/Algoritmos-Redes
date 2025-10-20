#!/usr/bin/env python3
import json, math, argparse
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="data/osm_sector.json")
ap.add_argument("--out", default="json/infra_provi_sector.geojson")
args = ap.parse_args()

def haversine_m(a,b):
    lat1,lon1=a; lat2,lon2=b
    R=6371000.0
    dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
    y=math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(y))

def main():
    data=json.loads(Path(args.src).read_text())
    feats=[]; eid=1
    for w in data.get("elements",[]):
        if w.get("type")!="way": continue
        g=w.get("geometry",[])
        if len(g)<2: continue
        latlon=[(n["lat"],n["lon"]) for n in g]
        length=sum(haversine_m(latlon[i],latlon[i+1]) for i in range(len(latlon)-1))
        props={"id":eid,"osm_id":w.get("id"),"highway":w.get("tags",{}).get("highway"),
               "oneway":w.get("tags",{}).get("oneway") in ("yes","1","true"),"length_m":round(length,2)}
        coords=[[p[1],p[0]] for p in latlon]
        feats.append({"type":"Feature","geometry":{"type":"LineString","coordinates":coords},"properties":props})
        eid+=1
    out=Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type":"FeatureCollection","features":feats,"crs":{"type":"name","properties":{"name":"EPSG:4326"}}}, ensure_ascii=False))
    print(f"OK:{out} features={len(feats)}")

if __name__=="__main__":
    main()
