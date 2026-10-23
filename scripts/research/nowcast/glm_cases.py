"""Rayos del GOES (GLM) a ≤ 100 km de cada caso con hora, de t−120 a t+30 min (UTC = hora local + 3 h).
Mismos casos que scripts/glm/glm_batch.py (con hora; sin granizo chico). Un CSV por caso: minutos respecto de la hora
reportada (negativo = antes), lat, lon, distancia en km y energía (fJ). Reanudable; ~40 min y ~8 GB de descarga.
Uso: python3 glm_cases.py [salida=.cache/research-nowcast/glm] [casos=data/events.json]"""
import csv
import io
import json
import math
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
events = json.loads((ROOT / "data/events.json").read_text())
G19 = datetime(2025, 4, 7)
BEFORE, AFTER, RADIUS = 120, 30, 100


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == 3:
                raise


def keys_for(bucket, hour):
    xml = get(f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix=GLM-L2-LCFA/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/").decode()
    return re.findall(r"<Key>([^<]+)</Key>", xml)


def start_of(key):
    y, doy, hh, mm, ss = (int(x) for x in re.search(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})", key).groups())
    return datetime(y, 1, 1) + timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss)


def flashes(bucket, key, lat0, lon0, t0):
    try:
        data = get(f"https://{bucket}.s3.amazonaws.com/{key}")
    except Exception:
        return None
    with h5py.File(io.BytesIO(data), "r") as f:
        if "flash_lat" not in f:
            return []
        lat = f["flash_lat"][:].astype(float)
        lon = f["flash_lon"][:].astype(float)
        en = f["flash_energy"][:].astype(float) if "flash_energy" in f else np.zeros(len(lat))
        sf = f["flash_energy"].attrs.get("scale_factor", [1.0])[0] if "flash_energy" in f else 1.0
        ao = f["flash_energy"].attrs.get("add_offset", [0.0])[0] if "flash_energy" in f else 0.0
    en = en * sf + ao
    dy = (lat - lat0) * 111.32
    dx = (lon - lon0) * 111.32 * math.cos(math.radians(lat0))
    d = np.hypot(dx, dy)
    m = (start_of(key) - t0).total_seconds() / 60
    return [(round(m, 2), round(a, 4), round(b, 4), round(c, 2), round(e * 1e15, 2)) for a, b, c, e in zip(lat[d <= RADIUS], lon[d <= RADIUS], d[d <= RADIUS], en[d <= RADIUS])]


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache/research-nowcast/glm"
    out.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 2:
        events = json.loads(Path(sys.argv[2]).read_text())
    cases = [e for e in events if e["localTime"] and not (e["type"] == "hail" and e["damaging"] is False)]
    print(len(cases), "casos", flush=True)
    for e in cases:
        path = out / f"{e['id']}.csv"
        if path.exists():
            continue
        t0 = datetime.fromisoformat(f"{e['date']}T{e['localTime']}") + timedelta(hours=3)
        start, end = t0 - timedelta(minutes=BEFORE), t0 + timedelta(minutes=AFTER)
        bucket = "noaa-goes19" if t0 >= G19 else "noaa-goes16"
        keys, hour = [], start.replace(minute=0, second=0)
        while hour <= end:
            keys += [k for k in keys_for(bucket, hour) if start <= start_of(k) < end]
            hour += timedelta(hours=1)
        with ThreadPoolExecutor(max_workers=24) as pool:
            res = list(pool.map(lambda k: flashes(bucket, k, e["lat"], e["lon"], t0), keys))
        missing = sum(r is None for r in res)
        rows = [row for r in res if r for row in r]
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["min", "lat", "lon", "km", "energy_fJ"])
            w.writerows(sorted(rows))
        (out / f"{e['id']}.meta.json").write_text(json.dumps({"files": len(keys), "missing": missing, "bucket": bucket, "t0_utc": t0.isoformat()}))
        print(e["id"], len(keys), "archivos,", missing, "faltan,", len(rows), "rayos", flush=True)
    print("LISTO", flush=True)
