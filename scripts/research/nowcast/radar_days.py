"""Radar de REDEMET (Santiago y Canguçu, Brasil) alrededor de cada caso, durante todo el día local (03–03 UTC).

Para cada caso a ≤ 330 km de alguno de los dos radares baja el maxcappi (máximo de la columna, cada 20 min, 400 km),
pasa los colores a dBZ (redemet_dbz.py) y guarda un recorte de ±40 km alrededor
del punto por imagen. Necesita REDEMET_API_KEY. Reanudable. Salida: un .npz por caso y radar/producto con `utc` (minutos
desde las 00:00 locales), `dbz` (recortes, NaN = sin eco) y `km` (distancia de cada píxel al punto).
Uso: REDEMET_API_KEY=... python3 radar_days.py [salida=.cache/research-nowcast/radar] [casos=data/events.json]"""
import io
import json
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

import redemet_dbz
from motor import ROOT, events

out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache/research-nowcast/radar"
out.mkdir(parents=True, exist_ok=True)
if len(sys.argv) > 2:
    events = {e["id"]: e for e in json.loads(Path(sys.argv[2]).read_text())}
KEY = os.environ["REDEMET_API_KEY"]
RADARS = {"sg": (-29.225213, -54.930257), "cn": (-31.404, -52.701644)}
PRODUCTS = {"maxcappi": 330}  # alcance útil en km (los CAPPI de 3–10 km casi no tienen archivo: 1–7 imágenes por día)
CROP_KM = 40


def km(lat1, lon1, lat2, lon2):
    return 6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(math.radians(lat1)) *
                                          math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2))


def get(url, headers=None):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def frames(product, area, day_start):
    """Imágenes del día: la API devuelve hasta 15 cuadros (cada ~20 min) que terminan en la hora pedida."""
    seen = {}
    for h in range(4, 29, 5):
        hour = day_start + timedelta(hours=h)
        res = json.loads(get(f"https://api-redemet.decea.mil.br/produtos/radar/{product}?area={area}&anima=15&data={hour:%Y%m%d%H}",
                             {"X-Api-Key": KEY}))
        for f in res["data"]["radar"] if res.get("status") else []:  # sin archivo para esa fecha: status false
            f = f[0]
            if f["path"] and f["data"]:
                t = datetime.fromisoformat(f["data"])
                if day_start <= t < day_start + timedelta(days=1):
                    seen[f["data"]] = f
        time.sleep(0.3)
    return [seen[k] for k in sorted(seen)]


def crop(frame, lat0, lon0):
    img = np.array(Image.open(io.BytesIO(get(frame["path"]))).convert("RGBA"))
    lat, lon = redemet_dbz.grid(frame, img.shape[:2])
    rows = np.where(np.abs(lat - lat0) * 111.32 <= CROP_KM)[0]
    cols = np.where(np.abs(lon - lon0) * 111.32 * math.cos(math.radians(lat0)) <= CROP_KM)[0]
    sub = img[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    la, lo = np.meshgrid(lat[rows], lon[cols], indexing="ij")
    d = np.hypot((la - lat0) * 111.32, (lo - lon0) * 111.32 * math.cos(math.radians(lat0)))
    return redemet_dbz.decode(sub), d


for e in events.values():
    if e["type"] == "hail" and e["damaging"] is False:
        continue
    day_start = datetime.fromisoformat(f"{e['date']}T00:00") + timedelta(hours=3)
    for area, center in RADARS.items():
        dist = km(e["lat"], e["lon"], *center)
        for product, reach in PRODUCTS.items():
            path = out / f"{e['id']}.{area}.{product}.npz"
            if dist > reach or path.exists():
                continue
            fs = frames(product, area, day_start)
            with ThreadPoolExecutor(max_workers=8) as pool:
                crops = list(pool.map(lambda f: crop(f, e["lat"], e["lon"]), fs))
            utc = np.array([(datetime.fromisoformat(f["data"]) - day_start).total_seconds() / 60 for f in fs])
            shapes = {c[0].shape for c in crops}
            dbz = np.stack([c[0] for c in crops]) if len(shapes) == 1 else np.empty((0, 0, 0))
            np.savez_compressed(path, utc=utc, dbz=dbz, km=crops[0][1] if crops else np.empty((0, 0)), range_km=dist)
            mx = np.nanmax(np.where(crops[0][1] <= 10, dbz, np.nan), axis=(1, 2)) if len(dbz) else []
            print(e["id"], area, product, f"{dist:.0f} km", len(fs), "cuadros, máx ≤10 km:",
                  f"{np.nanmax(mx):.1f}" if len(mx) and not np.isnan(mx).all() else "—", flush=True)
print("LISTO", flush=True)
