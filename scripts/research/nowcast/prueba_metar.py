"""Prueba independiente del aviso "Ahora" con casos que no se usaron para elegirlo: granizo y tormentas sin granizo
reportados por METAR en aeropuertos del sur de Brasil y en Melo (casos_metar.py), con el nivel del motor de
niveles_metar.ts y los rayos de glm_cases.py. La regla queda fija (la de src/engine/config.ts): no se reajusta nada.

Uso: python3 prueba_metar.py [carpeta de rayos=.cache/research-nowcast/glm]
"""
import csv
import sys
from pathlib import Path

import numpy as np

from motor import ROOT, engine_level, events, metar

GLM = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache/research-nowcast/glm"
W, DELAYS = 30, (10, 20)
RULE = (20, 3)
RADII, COUNTS = (10, 20, 30, 50), (1, 3, 10, 30)


def load(source, shift):
    out = []
    for cid, e in source.items():
        if not e["localTime"] or (e["type"] == "hail" and e["damaging"] is False) or not (GLM / f"{cid}.csv").exists():
            continue
        rows = list(csv.DictReader(open(GLM / f"{cid}.csv")))
        out.append({"id": cid, "e": e, "hail": e["type"] == "hail", "level": engine_level(cid),
                    "offset": -shift if shift and e["type"] == "hail" and "hora previa" in e["evidence"] else 0,
                    "min": np.array([float(r["min"]) for r in rows]), "km": np.array([float(r["km"]) for r in rows])})
    return out


def flashes(c, radius, delay):
    end = c["offset"] - delay
    return int(((c["min"] >= end - W) & (c["min"] < end) & (c["km"] <= radius)).sum())


def report(name, cases, pred):
    y = np.array([c["hail"] for c in cases])
    pred = np.asarray(pred, bool)
    pod, pofd = pred[y].mean(), pred[~y].mean()
    print(f"  {name:58s} detecta {pred[y].sum():2d}/{y.sum()} ({pod:4.0%})   falsas alarmas {pred[~y].sum():2d}/{(~y).sum()} ({pofd:4.0%})   TSS {pod - pofd:+.2f}")


br = load(metar, 0)  # en casos_metar.json la hora de "hora previa" ya viene corrida
uy = load(events, 30)
with_level = [c for c in br if c["level"] is not None]
print(f"Aeropuertos del sur de Brasil y Melo: {sum(c['hail'] for c in br)} granizadas y {sum(not c['hail'] for c in br)} tormentas sin granizo con rayos;"
      f" {sum(c['hail'] for c in with_level)} y {sum(not c['hail'] for c in with_level)} con nivel del motor (el archivo de Open-Meteo empieza en 2021-03)\n")

for delay in DELAYS:
    print(f"Datos de {delay} min (rayos de la media hora que termina {delay} min antes):")
    report('motor "Algunas chances" o más, solo', with_level, [c["level"] >= 1 for c in with_level])
    report('motor "Chances reales", solo', with_level, [c["level"] >= 2 for c in with_level])
    report(f"≥{RULE[1]} rayos a ≤{RULE[0]} km, sin motor (todos los casos)", br, [flashes(c, RULE[0], delay) >= RULE[1] for c in br])
    report(f"≥{RULE[1]} rayos a ≤{RULE[0]} km, sin motor (casos con nivel)", with_level, [flashes(c, RULE[0], delay) >= RULE[1] for c in with_level])
    report(f'el aviso de la app: "Algunas chances" o más + ≥{RULE[1]} rayos a ≤{RULE[0]} km', with_level,
           [c["level"] >= 1 and flashes(c, RULE[0], delay) >= RULE[1] for c in with_level])
    report(f'"Chances reales" + ≥{RULE[1]} rayos a ≤{RULE[0]} km', with_level,
           [c["level"] >= 2 and flashes(c, RULE[0], delay) >= RULE[1] for c in with_level])
    print()

print("Uruguay (events.json) + sur de Brasil, datos de 20 min:")
pooled = [c for c in uy + br if c["level"] is not None]
report('motor "Algunas chances" o más, solo', pooled, [c["level"] >= 1 for c in pooled])
report('motor "Chances reales", solo', pooled, [c["level"] >= 2 for c in pooled])
report("el aviso de la app", pooled, [c["level"] >= 1 and flashes(c, RULE[0], 20) >= RULE[1] for c in pooled])
print('  tabla con motor ≥ "Algunas chances" (detecta/falsas):')
y = np.array([c["hail"] for c in pooled])
for r in RADII:
    cells = []
    for n in COUNTS:
        p = np.array([c["level"] >= 1 and flashes(c, r, 20) >= n for c in pooled])
        cells.append(f"≥{n} rayos {p[y].sum()}/{p[~y].sum()}")
    print(f"    ≤{r} km: " + "   ".join(cells))
print(f"  ({y.sum()} granizadas, {(~y).sum()} sin granizo)")

print("\nGranizadas del sur de Brasil y Melo (motor: 0 muy pocas, 1 algunas, 2 reales, — sin dato):")
for c in [c for c in br if c["hail"]]:
    first = next((t for t in range(-120 + W, 1) if flashes(c, RULE[0], -t) >= RULE[1]), None)
    print(f"  {c['e']['date']} {c['e']['localTime']} {c['e']['place'][:22]:22s} motor {'—' if c['level'] is None else c['level']}  "
          f"rayos ≤{RULE[0]} km en la media hora (datos de 20 min): {flashes(c, RULE[0], 20):4d}  "
          f"primer disparo: {f'{-first} min antes' if first is not None else '—'}")
