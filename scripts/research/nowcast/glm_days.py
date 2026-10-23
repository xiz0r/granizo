"""Rayos del GOES (GLM) a ≤ 60 km de cada caso durante TODO el día local (00–24 h de Uruguay = 03–03 UTC).

Sirve para medir el aviso "Ahora" como lo vive la persona: ¿en un día de tormenta sin granizo, salta en algún momento?
¿en un día de granizo, salta y cuándo? Solo los casos donde el motor ve al menos "Algunas chances" (sin eso el aviso no
puede saltar). Un CSV por caso: minutos desde las 00:00 locales, lat, lon y distancia en km. Reanudable.
~2–5 min y ~1 GB de descarga por caso.
Uso: python3 glm_days.py [salida=.cache/research-nowcast/glm-days] [hilos=48] [casos=data/events.json]"""
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from glm_cases import G19, ROOT, flashes, keys_for, start_of
from motor import engine_level, events

out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache/research-nowcast/glm-days"
threads = int(sys.argv[2]) if len(sys.argv) > 2 else 48
out.mkdir(parents=True, exist_ok=True)
RADIUS = 60

if len(sys.argv) > 3:
    events = {e["id"]: e for e in json.loads(Path(sys.argv[3]).read_text())}
cases = [e for e in events.values()
         if not (e["type"] == "hail" and e["damaging"] is False) and (engine_level(e["id"]) or 0) >= 1]
print(len(cases), "casos", flush=True)
for e in cases:
    path = out / f"{e['id']}.csv"
    if path.exists():
        continue
    t0 = datetime.fromisoformat(f"{e['date']}T00:00") + timedelta(hours=3)
    end = t0 + timedelta(days=1)
    bucket = "noaa-goes19" if t0 >= G19 else "noaa-goes16"
    keys = [k for h in range(24) for k in keys_for(bucket, t0 + timedelta(hours=h)) if t0 <= start_of(k) < end]
    with ThreadPoolExecutor(max_workers=threads) as pool:
        res = list(pool.map(lambda k: flashes(bucket, k, e["lat"], e["lon"], t0), keys))
    missing = sum(r is None for r in res)
    rows = [row[:4] for r in res if r for row in r if row[3] <= RADIUS]
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["min", "lat", "lon", "km"])
        w.writerows(sorted(rows))
    (out / f"{e['id']}.meta.json").write_text(json.dumps({"files": len(keys), "missing": missing, "bucket": bucket}))
    print(e["id"], len(keys), "archivos,", missing, "faltan,", len(rows), "rayos", flush=True)
print("LISTO", flush=True)
