#!/usr/bin/env python3
import json, sys, time, argparse
from pathlib import Path
import requests, yaml

ap = argparse.ArgumentParser()
ap.add_argument("--cfg", default="etl/infraestructura/infra_sector.yaml")
args = ap.parse_args()

cfg = yaml.safe_load(Path(args.cfg).read_text())
UA = cfg.get("user_agent","Mozilla/5.0 (compatible; fase2/1.0)")
TIMEOUT = int(cfg.get("timeout_s",120))
URL = cfg.get("overpass_url","https://z.overpass-api.de/api/interpreter")
S,W,N,E = cfg["bbox"]

QUERY = f"""[bbox:{S},{W},{N},{E}][out:json][timeout:{TIMEOUT}];
way["highway"]; out geom;"""

def fetch(url):
    r = requests.get(url, params={"data": QUERY}, headers={"User-Agent": UA, "Accept":"application/json"}, timeout=TIMEOUT+15)
    if r.status_code != 200:
        r = requests.post(url, data={"data": QUERY}, headers={"User-Agent": UA, "Accept":"application/json","Content-Type":"application/x-www-form-urlencoded"}, timeout=TIMEOUT+15)
    r.raise_for_status()
    return r.json()

def main():
    Path("data").mkdir(parents=True, exist_ok=True)
    j = fetch(URL)
    Path("data/osm_sector.json").write_text(json.dumps({"bbox":[S,W,N,E],"elements":j.get("elements",[])}, ensure_ascii=False))
    ways = sum(1 for e in j.get("elements",[]) if e.get("type")=="way")
    print(f"OK:data/osm_sector.json ways={ways} bbox=[{S},{W},{N},{E}]")

if __name__=="__main__":
    main()
