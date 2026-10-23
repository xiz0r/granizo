"""¿La lluvia estimada por satélite (RRQPE) antes del granizo suma algo a los rayos y al motor?

Lee rrqpe_cases.py y los rayos de glm_cases.py. Como el aviso: lo que se sabía en la media hora que termina 20 min antes
(máximo de mm/h a ≤ 20 km en esas imágenes). Casos de Uruguay (events.json) y del sur de Brasil (casos_metar.json).
Uso: python3 evaluar_lluvia.py
"""
import csv
import json

import numpy as np

from motor import ROOT, all_cases, engine_level

RR = json.loads((ROOT / ".cache/research-nowcast/rrqpe.json").read_text())
GLM = ROOT / ".cache/research-nowcast/glm"
DELAY, W, R = 20, 30, "20"
LEVELS = (1, 5, 10, 20, 30, 50)

cases = []
for cid, imgs in RR.items():
    e = all_cases[cid]
    shift = 30 if not cid.startswith("metar-") and e["type"] == "hail" and "hora previa" in e["evidence"] else 0
    end = -shift - DELAY
    rain = [x[R] for x in imgs if end - W <= x["min"] < end and x[R] is not None]
    rows = list(csv.DictReader(open(GLM / f"{cid}.csv"))) if (GLM / f"{cid}.csv").exists() else []
    fl = sum(1 for r in rows if end - W <= float(r["min"]) < end and float(r["km"]) <= 20)
    cases.append({"hail": e["type"] == "hail", "level": engine_level(cid), "rain": max(rain) if rain else np.nan, "flashes": fl})


def auc(pos, neg):
    return np.mean([(p > neg).mean() + 0.5 * (p == neg).mean() for p in pos])


def table(name, sub):
    y = np.array([c["hail"] for c in sub])
    v = np.array([c["rain"] for c in sub])
    ok = ~np.isnan(v)
    y, v = y[ok], v[ok]
    print(f"{name}: {y.sum()} granizadas, {(~y).sum()} sin granizo   AUC lluvia {auc(v[y], v[~y]):.2f}")
    print("    " + "   ".join(f"≥{lv} mm/h: {(v[y] >= lv).sum()}/{y.sum()} vs {(v[~y] >= lv).sum()}/{(~y).sum()}" for lv in LEVELS))


table("Todos los casos con hora", cases)
table('Motor ≥ "Algunas chances"', [c for c in cases if c["level"] is not None and c["level"] >= 1])
table('Motor ≥ "Algunas chances" y ≥ 3 rayos a ≤ 20 km (ya saltó el aviso)',
      [c for c in cases if c["level"] is not None and c["level"] >= 1 and c["flashes"] >= 3])
fl = [c for c in cases if c["flashes"] >= 3]
table("Con ≥ 3 rayos a ≤ 20 km, sin mirar el motor", fl)
