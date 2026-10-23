"""Rayos de la última media hora cerca de Uruguay, en un JSON para el aviso "Ahora" de la app.

Lo corre .github/workflows/nowcast.yml cada 10 minutos y lo publica en la rama `nowcast` (latest.json).
Fuente: GOES-19 GLM (NOAA, bucket público noaa-goes19, un archivo cada 20 s, ~10–30 s de latencia). Sin claves.

Solo trae lo que la app usa y lo que pasó la prueba (scripts/research/nowcast/README.md). Se probaron y quedaron afuera la
lluvia estimada por satélite (no suma nada a los rayos) y el radar de REDEMET (llega tarde para avisar antes del granizo,
cubre solo el norte y el este, y en una muestra grande distinguió poco).

Uso: python3 scripts/nowcast/build.py [salida=nowcast/latest.json]
Sale con error si no pudo armarlo (así la rama conserva el último JSON bueno).
"""
import io
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "glm"))
from glm_point import file_start, list_keys  # noqa: E402

VERSION = 2
# Uruguay y ~80 km alrededor: por ahí llegan las tormentas que importan en la próxima hora.
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = -35.8, -29.0, -59.5, -52.0
CELL_DEG = 0.1
WINDOW_MIN = 30
SLOT_MIN = 10
GLM_BUCKET = "noaa-goes19"


def get(url, timeout=60, attempts=3):
    """GET con reintentos: S3 a veces corta la conexión a mitad de la respuesta."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == attempts - 1:
                raise


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def flashes_in_zone(key):
    with h5py.File(io.BytesIO(get(f"https://{GLM_BUCKET}.s3.amazonaws.com/{key}")), "r") as f:
        if "flash_lat" not in f:
            return np.empty(0), np.empty(0)
        lat = f["flash_lat"][:].astype(float)
        lon = f["flash_lon"][:].astype(float)
    inside = (lat >= LAT_MIN) & (lat <= LAT_MAX) & (lon >= LON_MIN) & (lon <= LON_MAX)
    return lat[inside], lon[inside]


def lightning(now):
    end = now - timedelta(minutes=1)  # los archivos se publican ~10–30 s después de cerrar
    start = end - timedelta(minutes=WINDOW_MIN)
    keys = []
    hour = start.replace(minute=0, second=0, microsecond=0)
    while hour <= end:
        keys += [k for k in list_keys(GLM_BUCKET, hour) if start <= file_start(k) < end]
        hour += timedelta(hours=1)

    def load(key):
        try:
            return file_start(key), *flashes_in_zone(key)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=16) as pool:
        files = [f for f in pool.map(load, keys) if f is not None]
    if not files:
        raise RuntimeError("sin archivos GLM en la ventana")

    times = np.concatenate([np.full(len(lat), (end - ts).total_seconds() / 60) for ts, lat, _ in files])
    lat = np.concatenate([f[1] for f in files])
    lon = np.concatenate([f[2] for f in files])
    slot = np.minimum((times // SLOT_MIN).astype(int), WINDOW_MIN // SLOT_MIN - 1)  # 0 = últimos 10 min

    grid = {}
    rows = np.floor((lat - LAT_MIN) / CELL_DEG).astype(int)
    cols = np.floor((lon - LON_MIN) / CELL_DEG).astype(int)
    for i, j, s in zip(rows, cols, slot):
        grid.setdefault((i, j), [0] * (WINDOW_MIN // SLOT_MIN))[s] += 1
    cells = [[round(LAT_MIN + (i + 0.5) * CELL_DEG, 2), round(LON_MIN + (j + 0.5) * CELL_DEG, 2), *counts]
             for (i, j), counts in sorted(grid.items())]
    return {
        "source": "GOES-19 GLM (NOAA)",
        "fromUtc": iso(start),
        "toUtc": iso(end),
        "files": len(files),
        "missingFiles": len(keys) - len(files),
        "flashes": int(len(lat)),
        # [lat, lon, rayos últimos 10 min, 10–20 min antes, 20–30 min antes] por celda de 0,1° con algún rayo.
        "grid": {"cellDeg": CELL_DEG, "slotMin": SLOT_MIN, "cells": cells},
    }


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "nowcast/latest.json")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    doc = {"version": VERSION, "generatedUtc": iso(now),
           "zone": {"latMin": LAT_MIN, "latMax": LAT_MAX, "lonMin": LON_MIN, "lonMax": LON_MAX},
           "lightning": lightning(now)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"{target}: {target.stat().st_size / 1000:.1f} kB · {doc['lightning']['flashes']} rayos en "
          f"{len(doc['lightning']['grid']['cells'])} celdas")


if __name__ == "__main__":
    main()
