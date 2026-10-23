"""El aviso "Ahora" sobre los pronósticos reales guardados (data/forecast-log/runs/), no sobre casos elegidos.

Los casos de prueba son todos días en que una tormenta pasó por el lugar, así que ahí los rayos cerca aparecen casi
siempre. Pero muchas veces el motor dice "Algunas chances" y la tormenta nunca llega: este script mide eso. Para cada
ventana del registro (corrida de las 12 UTC del día anterior, 16 ciudades) con "Algunas chances" o más, simula la app
cada 10 minutos con los rayos del GOES (datos de 20 min) y cuenta en cuántas ventanas habría saltado "cubrilo ahora".
También cruza con las granizadas de data/events.json a ≤ 40 km de una ciudad del registro.

Baja los rayos de las horas que hacen falta a .cache/research-nowcast/glm-log/ (reanudable, ~1 min por hora de datos).
Uso: python3 registro_rayos.py
"""
import csv
import glob
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import h5py
import numpy as np

from glm_cases import G19, get, keys_for, start_of
from motor import ROOT, events

CACHE = ROOT / ".cache/research-nowcast/glm-log"
CACHE.mkdir(parents=True, exist_ok=True)
WINDOWS = ("tonight", "tomorrow", "tomorrow_night")
RADIUS, COUNT, DELAY, W = 20, 3, 20, 30
KEEP_KM = 60

log = [json.loads(line) for f in sorted(glob.glob(str(ROOT / "data/forecast-log/runs/*.jsonl"))) for line in open(f)]
log = [r for r in log if r["window"] in WINDOWS]
cities = {r["city"]: (r["lat"], r["lon"]) for r in log}
utc = lambda local: datetime.fromisoformat(local) + timedelta(hours=3)


def near_any(lat, lon):
    keep = np.zeros(len(lat), bool)
    for clat, clon in cities.values():
        d = np.hypot((lat - clat) * 111.32, (lon - clon) * 111.32 * math.cos(math.radians(clat)))
        keep |= d <= KEEP_KM
    return keep


def hour_flashes(hour):
    path = CACHE / f"{hour:%Y%m%d%H}.csv"
    if not path.exists():
        bucket = "noaa-goes19" if hour >= G19 else "noaa-goes16"
        keys = keys_for(bucket, hour)

        def one(key):
            try:
                with h5py.File(io.BytesIO(get(f"https://{bucket}.s3.amazonaws.com/{key}")), "r") as f:
                    if "flash_lat" not in f:
                        return []
                    lat, lon = f["flash_lat"][:].astype(float), f["flash_lon"][:].astype(float)
            except Exception:
                return None
            k = near_any(lat, lon)
            t = (start_of(key) - hour).total_seconds() / 60
            return [(round(t, 2), round(a, 4), round(b, 4)) for a, b in zip(lat[k], lon[k])]

        with ThreadPoolExecutor(max_workers=32) as pool:
            res = list(pool.map(one, keys))
        if len(keys) < 170 or sum(r is None for r in res) > 5:
            return None  # hora incompleta: no se guarda, se reintenta la próxima vez
        with path.open("w", newline="") as fh:
            csv.writer(fh).writerows(row for r in res if r for row in r)
    rows = list(csv.reader(open(path)))
    return np.array([[hour.timestamp() / 60 + float(t), float(a), float(b)] for t, a, b in rows]).reshape(-1, 3)


watch = [r for r in log if r["level"] != "calm"]
hours = sorted({utc(r["from"]).replace(minute=0) - timedelta(hours=1) + timedelta(hours=h)
                for r in watch for h in range(int((utc(r["to"]) - utc(r["from"])).total_seconds() // 3600) + 2)})
print(f"{len(watch)} ventanas con \"Algunas chances\" o más; {len(hours)} horas de rayos", flush=True)
flashes = {}
for i, h in enumerate(hours):
    flashes[h] = hour_flashes(h)
    if i % 24 == 0:
        print(f"  {i}/{len(hours)} {h:%Y-%m-%d %H} UTC", flush=True)
missing = sum(v is None for v in flashes.values())


def alert_ticks(r):
    clat, clon = r["lat"], r["lon"]
    start, end = utc(r["from"]), utc(r["to"])
    hs = [h for h in flashes if start - timedelta(hours=1) <= h <= end]
    if any(flashes[h] is None for h in hs):
        return None, None
    f = np.concatenate([flashes[h] for h in hs]) if hs else np.empty((0, 3))
    d = np.hypot((f[:, 1] - clat) * 111.32, (f[:, 2] - clon) * 111.32 * math.cos(math.radians(clat)))
    t = np.sort(f[d <= RADIUS, 0])
    ticks = np.arange(start.timestamp() / 60, end.timestamp() / 60 + 1, 10)
    n = np.searchsorted(t, ticks - DELAY) - np.searchsorted(t, ticks - DELAY - W)
    return ticks, n >= COUNT


future = sum(h >= datetime.now(timezone.utc).replace(tzinfo=None) for h, v in flashes.items() if v is None)
print(f"(horas sin datos completos: {missing}; {future} todavía no pasaron, el resto son cortes del GLM)\n")
for level in ("watch", "protect"):
    sub = [r for r in watch if r["level"] == level]
    res = [alert_ticks(r) for r in sub]
    ok = [(r, a) for r, (t, a) in zip(sub, res) if a is not None]
    fired = sum(a.any() for _, a in ok)
    name = "Algunas chances" if level == "watch" else "Chances reales"
    print(f"\"{name}\": {len(ok)} ventanas de 12 h; el aviso habría saltado en {fired} ({fired / max(len(ok), 1):.0%})")
    for window in WINDOWS:
        w = [(r, a) for r, a in ok if r["window"] == window]
        if w:
            print(f"    {window:15s} {sum(a.any() for _, a in w)}/{len(w)}")

hail = [e for e in events.values() if e["type"] == "hail" and e["damaging"] is not False and e["date"] >= "2026-04-02"]
print("\nGranizadas desde abril de 2026 a ≤ 40 km de una ciudad del registro (ventana que la contiene):")
matched = 0
for e in hail:
    for city, (clat, clon) in cities.items():
        if math.hypot((e["lat"] - clat) * 111.32, (e["lon"] - clon) * 111.32 * math.cos(math.radians(clat))) > 40:
            continue
        when = f"{e['date']}T{e['localTime'] or '12:00'}"
        rs = [r for r in log if r["city"] == city and r["from"] <= when < r["to"] and r["window"] in ("tonight", "tomorrow")]
        for r in rs:
            matched += 1
            t, a = alert_ticks(r) if r["level"] != "calm" else (None, None)
            print(f"  {e['date']} {e['localTime'] or '—':5s} {e['place'][:24]:24s} → {city:12s} {r['window']:9s} nivel {r['level']:7s} "
                  + ("aviso: " + ("sí" if a.any() else "no") if a is not None else "aviso: — (sin rayos bajados o nivel calm)"))
if not matched:
    print("  ninguna: las granizadas de 2026 fueron lejos de las 4 ciudades que el registro sigue desde abril"
          " (las otras 12 entraron en octubre)")
