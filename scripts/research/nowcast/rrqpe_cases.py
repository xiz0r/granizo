"""Lluvia estimada por satélite (GOES ABI RRQPE, disco completo cada 10 min) alrededor de cada caso con hora.

Es el mismo algoritmo que la lluvia del JSON (que usa la mezcla de satélites de NOAA, archivada solo desde 2025-02).
Para cada caso guarda el máximo en mm/h a ≤ 10, 20 y 30 km en cada imagen de t−90 a t+10 min. Sin cuenta, reanudable.
Uso: python3 rrqpe_cases.py [salida=.cache/research-nowcast/rrqpe.json]"""
import io
import json
import math
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import h5py
import numpy as np

from glm_cases import G19, get, start_of
from motor import ROOT, all_cases

out_path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / ".cache/research-nowcast/rrqpe.json")
done = json.loads(open(out_path).read()) if os.path.exists(out_path) else {}
BEFORE, AFTER, RADII = 90, 10, (10, 20, 30)


def scan_angles(f, lat, lon):
    """lat/lon (grados) → índices de fila y columna de la grilla fija del GOES."""
    p = f["goes_imager_projection"].attrs
    a, b = float(p["semi_major_axis"][0]), float(p["semi_minor_axis"][0])
    h = float(p["perspective_point_height"][0]) + a
    lon0 = math.radians(float(p["longitude_of_projection_origin"][0]))
    lat, lon = np.radians(lat), np.radians(lon)
    phi = np.arctan((b * b) / (a * a) * np.tan(lat))
    e2 = (a * a - b * b) / (a * a)
    rc = b / np.sqrt(1 - e2 * np.cos(phi) ** 2)
    sx = h - rc * np.cos(phi) * np.cos(lon - lon0)
    sy = -rc * np.cos(phi) * np.sin(lon - lon0)
    sz = rc * np.sin(phi)
    x = np.arcsin(-sy / np.sqrt(sx * sx + sy * sy + sz * sz))
    y = np.arctan(sz / sx)
    xs, ys = f["x"], f["y"]
    xi = np.rint((x - xs.attrs["add_offset"][0]) / xs.attrs["scale_factor"][0]).astype(int)
    yi = np.rint((y - ys.attrs["add_offset"][0]) / ys.attrs["scale_factor"][0]).astype(int)
    return yi, xi


def maxima(bucket, key, lat0, lon0):
    try:
        data = get(f"https://{bucket}.s3.amazonaws.com/{key}")
    except Exception:
        return None
    dy, dx = np.meshgrid(np.arange(-32, 33) * 1.0, np.arange(-32, 33) * 1.0, indexing="ij")  # km
    lat = lat0 + dy / 111.32
    lon = lon0 + dx / (111.32 * math.cos(math.radians(lat0)))
    d = np.hypot(dx, dy)
    with h5py.File(io.BytesIO(data), "r") as f:
        yi, xi = scan_angles(f, lat, lon)
        v = f["RRQPE"]
        r0, r1, c0, c1 = yi.min(), yi.max() + 1, xi.min(), xi.max() + 1
        raw = v[r0:r1, c0:c1].astype(float)
        fill = v.attrs.get("_FillValue", [None])[0]
        rate = raw * v.attrs.get("scale_factor", [1.0])[0] + v.attrs.get("add_offset", [0.0])[0]
        if fill is not None:
            rate[raw == fill] = np.nan
        sample = rate[yi - r0, xi - c0]
    return {str(r): (float(np.nanmax(np.where(d <= r, sample, np.nan))) if np.isfinite(sample[d <= r]).any() else None) for r in RADII}


cases = [e for e in all_cases.values() if e["localTime"] and not (e["type"] == "hail" and e["damaging"] is False)]
print(len(cases), "casos", flush=True)
for e in cases:
    if e["id"] in done:
        continue
    t0 = datetime.fromisoformat(f"{e['date']}T{e['localTime']}") + timedelta(hours=3)
    start, end = t0 - timedelta(minutes=BEFORE), t0 + timedelta(minutes=AFTER)
    bucket = "noaa-goes19" if t0 >= G19 else "noaa-goes16"
    keys, hour = [], start.replace(minute=0, second=0)
    while hour <= end:
        xml = get(f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-RRQPEF/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/").decode()
        keys += [k for k in re.findall(r"<Key>([^<]+)</Key>", xml) if start <= start_of(k) < end]
        hour += timedelta(hours=1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        res = list(pool.map(lambda k: maxima(bucket, k, e["lat"], e["lon"]), keys))
    done[e["id"]] = [{"min": round((start_of(k) - t0).total_seconds() / 60, 1), **r} for k, r in zip(keys, res) if r]
    open(out_path, "w").write(json.dumps(done))
    best = max((x["20"] or 0 for x in done[e["id"]]), default=None)
    print(e["id"], len(keys), "imágenes, máx ≤20 km:", best, flush=True)
print("LISTO", flush=True)
