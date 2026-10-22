"""Calibración del aviso "Ahora": nivel del motor para el día + rayos del GOES ANTES del granizo.

Lee data/events.json, reports/backtest.csv (pico v0.2.0 por caso, combinado), reports/ecmwf-eval.json (pico de cada
modelo desde 2024-06) y los rayos por caso de glm_cases.py. Sin red.

- Nivel del motor (v0.2.1) por caso, a partir del pico guardado: "Chances reales" no cambió; "Algunas chances" pide
  WMAXSHEAR ≥ 900 (o ambiente fuerte sin tormentas en el modelo); dos modelos con la regla "both".
- Solo cuenta lo que se sabía antes del granizo: los rayos de la media hora que termina `demora` minutos antes de la
  hora reportada (la app ve datos de 10–25 min: cron cada 10 min + demoras de GitHub + caché de 5 min).
- Las granizadas que un METAR reporta "en la hora previa" (REGR, RETSGR…) se corren `corrimiento` minutos hacia atrás.
- Radio y cantidad se eligen por TSS; la validación cruzada deja una fecha afuera y elige con el resto.

Uso: python3 evaluar.py [carpeta de rayos=.cache/research-nowcast/glm] [corrimiento=30]
"""
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
GLM = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache/research-nowcast/glm"
SHIFT = int(sys.argv[2]) if len(sys.argv) > 2 else 30
W = 30  # minutos de rayos que mira el aviso (los del JSON)
RADII, COUNTS, DELAYS = (20, 30, 50), (1, 3, 10, 30), (10, 20)
RULE = {"radius": 20, "flashes": 3}  # lo que usa src/engine/config.ts (NOWCAST)

events = {e["id"]: e for e in json.loads((ROOT / "data/events.json").read_text())}
backtest = {r["id"]: r for r in csv.DictReader(open(ROOT / "reports/backtest.csv"))}
by_model = json.loads((ROOT / "reports/ecmwf-eval.json").read_text())
num = lambda x: None if x in ("", "—", None) else float(x)


def model_level(level, env, lapse, wmax):
    if level == "protect":
        return 2
    if env == "strong" or (lapse is not None and wmax is not None and lapse >= 6.5 and wmax >= 900):
        return 1
    return 0


def engine_level(cid):
    if cid in by_model:
        levels = [model_level(m["level"], m["env"], m["lapse"], m["wmax"]) for m in (by_model[cid].get("gfs_seamless"), by_model[cid].get("ecmwf_ifs025")) if m]
        if len(levels) == 2:
            a, b = levels
            return 2 if a == 2 and b == 2 else 1 if (2 in levels or (a >= 1 and b >= 1)) else 0
        return levels[0]
    r = backtest[cid]
    mu, shear = num(r["mucape"]), num(r["shear06"])
    wmax = math.sqrt(2 * mu) * shear if mu is not None and shear is not None else None
    return model_level(r["level"], r["environment"], num(r["lapse"]), wmax)


cases = []
for cid, e in events.items():
    if not e["localTime"] or (e["type"] == "hail" and e["damaging"] is False) or not (GLM / f"{cid}.csv").exists():
        continue
    rows = list(csv.DictReader(open(GLM / f"{cid}.csv")))
    cases.append({
        "id": cid, "date": e["date"], "hail": e["type"] == "hail", "level": engine_level(cid),
        "offset": -SHIFT if e["type"] == "hail" and "hora previa" in e["evidence"] else 0,
        "min": np.array([float(r["min"]) for r in rows]), "km": np.array([float(r["km"]) for r in rows]),
        "lat": np.array([float(r["lat"]) for r in rows]), "lon": np.array([float(r["lon"]) for r in rows]), "event": e,
    })
y = np.array([c["hail"] for c in cases])
dates = np.array([c["date"] for c in cases])
level = np.array([c["level"] for c in cases])
print(f"{len(cases)} casos con hora: {y.sum()} granizadas, {(~y).sum()} tormentas sin granizo; "
      f"corrimiento de los METAR 'hora previa': {SHIFT} min ({sum(1 for c in cases if c['offset'])} casos)\n")


def flashes(c, radius, delay, cell=None):
    """Rayos a ≤ radius km en la media hora que termina `delay` min antes del granizo. Con `cell`, como la app: sumando
    las celdas del JSON cuyo centro queda a ≤ radius km."""
    end = c["offset"] - delay
    sel = (c["min"] >= end - W) & (c["min"] < end)
    if cell is None:
        return int((sel & (c["km"] <= radius)).sum())
    e = c["event"]
    clat = -35.8 + (np.floor((c["lat"][sel] + 35.8) / cell) + 0.5) * cell
    clon = -59.5 + (np.floor((c["lon"][sel] + 59.5) / cell) + 0.5) * cell
    d = np.hypot((clat - e["lat"]) * 111.32, (clon - e["lon"]) * 111.32 * math.cos(math.radians(e["lat"])))
    return int((d <= radius).sum())


def tss(pred, idx=None):
    idx = np.arange(len(y)) if idx is None else idx
    yy, pp = y[idx], pred[idx]
    return pp[yy].mean() - pp[~yy].mean() if yy.any() and (~yy).any() else np.nan


def line(name, pred):
    print(f"  {name:52s} detecta {pred[y].sum():2d}/{y.sum()} ({pred[y].mean():4.0%})   "
          f"falsas alarmas {pred[~y].sum():2d}/{(~y).sum()} ({pred[~y].mean():4.0%})   TSS {tss(pred):+.2f}")


print("Motor solo (nivel del día):")
line('"Algunas chances" o más', level >= 1)
line('"Chances reales"', level >= 2)

gates = {"sin motor": level >= 0, 'motor ≥ "Algunas chances"': level >= 1, 'motor "Chances reales"': level >= 2}
for delay in DELAYS:
    pred = {(r, n): np.array([flashes(c, r, delay) >= n for c in cases]) for r in RADII for n in COUNTS}
    print(f"\nRayos de la media hora que termina {delay} min antes del granizo:")
    for gname, gate in gates.items():
        oof = np.zeros(len(y), bool)
        for d in np.unique(dates):
            train = np.where(dates != d)[0]
            best = max(pred, key=lambda k: (np.nan_to_num(tss(pred[k] & gate, train), nan=-9), -k[0], k[1]))
            oof[dates == d] = (pred[best] & gate)[dates == d]
        rule = pred[(RULE["radius"], RULE["flashes"])] & gate
        print(f"  {gname}: regla ≤{RULE['radius']} km y ≥{RULE['flashes']} rayos → detecta {rule[y].sum()}/{y.sum()}, falsas {rule[~y].sum()}/{(~y).sum()}"
              f" | validación cruzada (elige radio y cantidad sin la fecha): detecta {oof[y].mean():.0%}, falsas {oof[~y].mean():.0%}")
    print('  tabla con motor ≥ "Algunas chances" (detecta/falsas):')
    for r in RADII:
        print(f"    ≤{r} km: " + "   ".join(f"≥{n} rayos {(pred[(r, n)] & (level >= 1))[y].sum()}/{(pred[(r, n)] & (level >= 1))[~y].sum()}" for n in COUNTS))

print(f"\nGranizadas, regla ≤{RULE['radius']} km y ≥{RULE['flashes']} rayos (motor: 0 muy pocas, 1 algunas, 2 reales):")
for c in [c for c in cases if c["hail"]]:
    first = next((t for t in range(-120 + W, 1) if flashes(c, RULE["radius"], -t) >= RULE["flashes"]), None)
    print(f"  {c['date']} {c['event']['localTime']} {c['event']['place'][:28]:28s} motor {c['level']}  "
          f"rayos con datos de 10 min: {'sí' if flashes(c, RULE['radius'], 10) >= RULE['flashes'] else 'no'}, de 20 min: "
          f"{'sí' if flashes(c, RULE['radius'], 20) >= RULE['flashes'] else 'no'}  primer disparo: {f'{-first} min antes' if first is not None else '—'}")

same = sum((flashes(c, RULE["radius"], 20, cell=0.1) >= RULE["flashes"]) == (flashes(c, RULE["radius"], 20) >= RULE["flashes"]) for c in cases)
print(f"\nCon las celdas de 0,1° del JSON la regla da lo mismo que con la distancia exacta en {same}/{len(cases)} casos.")
