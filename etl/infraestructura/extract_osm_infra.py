#!/usr/bin/env python3
import json, time, sys, math, random
from pathlib import Path
import requests, yaml

cfg = yaml.safe_load(Path(__file__).with_name("infra_config.yaml").read_text())
UA = cfg.get("user_agent", "fase2-providencia-etl/infra/1.2")
TIMEOUT = int(cfg.get("timeout_s", 120))
URLS = cfg.get("overpass_urls") or [cfg.get("overpass_url","https://overpass-api.de/api/interpreter")]

S,W,N,E = cfg["bbox"]

def tiles(nx=4, ny=4):
    for iy in range(ny):
        y0 = S + (N-S)*iy/ny
        y1 = S + (N-S)*(iy+1)/ny
        for ix in range(nx):
            x0 = W + (E-W)*ix/nx
            x1 = W + (E-W)*(ix+1)/nx
            yield (y0,x0,y1,x1)

def overpass_post(q, urls):
    last_err=None
    for url in urls:
        try:
            r = requests.post(url, data=q.encode("utf-8"),
                              headers={"User-Agent": UA, "Accept":"application/json"},
                              timeout=TIMEOUT+10)
            if r.status_code in (429, 502, 503, 504):
                time.sleep(2)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err=e
            time.sleep(1)
    raise RuntimeError(f"Overpass failure: {last_err}")

def fetch_tile(b):
    s,w,n,e = b
    q = f"""
    [out:json][timeout:{TIMEOUT}];
    (
      way["highway"][~"highway","{cfg["highway_regex"]}"]({s},{w},{n},{e});
    );
    out ids tags geom qt;
    """
    # shuffle URLs per tile
    urls = URLS[:]
    random.shuffle(urls)
    return overpass_post(q, urls)

def main():
    Path("data").mkdir(parents=True, exist_ok=True)
    seen=set()
    elements=[]
    nx, ny = 4, 4
    for i,b in enumerate(tiles(nx,ny),1):
        try:
            res = fetch_tile(b)
            for e in res.get("elements",[]):
                if e.get("type")=="way":
                    eid=e["id"]
                    if eid in seen: 
                        continue
                    seen.add(eid)
                    elements.append(e)
            print(f"[tile {i}/{nx*ny}] ways_acc={len(elements)}")
            time.sleep(0.5)
        except Exception as ex:
            print(f"[tile {i}] WARN {ex}", file=sys.stderr)
            time.sleep(1)

    out = Path("data/osm_providencia_highways.json")
    out.write_text(json.dumps({"bbox": cfg["bbox"], "elements": elements}, ensure_ascii=False))
    print(f"OK:{out} ways={len(elements)}")

if __name__ == "__main__":
    main()
