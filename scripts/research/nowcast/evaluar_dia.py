"""El aviso "Ahora" a lo largo de todo el día, como lo vería alguien que abre la app cada tanto.

Simula la app cada 10 minutos del día local con los rayos de glm_days.py: a las T, el JSON trae los rayos de la media
hora que termina `demora` minutos antes. Solo días donde el motor ve al menos "Algunas chances" (motor.py).

- Día de granizo con hora: ¿el aviso estuvo prendido en algún momento de las 2 horas previas? ¿desde cuándo?
- Cualquier día de granizo: ¿saltó en algún momento del día?
- Día de tormenta sin granizo: ¿saltó en algún momento del día? (falsa alarma "por día") y cuántas horas estuvo prendido.

Uso: python3 evaluar_dia.py [carpeta=.cache/research-nowcast/glm-days] [demora=20]
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

from motor import ROOT, all_cases, engine_level

DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache/research-nowcast/glm-days"
DELAY = int(sys.argv[2]) if len(sys.argv) > 2 else 20
W, STEP, BEFORE = 30, 10, 120
RADII, COUNTS = (10, 20, 30), (1, 3, 10, 30, 100)
RULE = (20, 3)

cases = []
for path in sorted(DIR.glob("*.csv")):
    cid = path.stem
    e = all_cases[cid]
    meta = json.loads((DIR / f"{cid}.meta.json").read_text())
    if meta["missing"] > 0.02 * meta["files"]:
        continue
    rows = list(csv.DictReader(open(path)))
    hail_min = None
    if e["type"] == "hail" and e["localTime"]:
        hh, mm = map(int, e["localTime"].split(":"))
        hail_min = hh * 60 + mm - (30 if not cid.startswith("metar-") and "hora previa" in e["evidence"] else 0)
    cases.append({"id": cid, "e": e, "hail": e["type"] == "hail", "level": engine_level(cid), "hail_min": hail_min,
                  "min": np.array([float(r["min"]) for r in rows]), "km": np.array([float(r["km"]) for r in rows])})
ticks = np.arange(0, 24 * 60 + 1, STEP)


def alerts(c, radius, count):
    """Aviso prendido (True/False) en cada tick del día."""
    near = c["min"][c["km"] <= radius]
    end = ticks - DELAY
    n = np.searchsorted(np.sort(near), end) - np.searchsorted(np.sort(near), end - W)
    return n >= count


def summary(radius, count, gate=1):
    hail = [c for c in cases if c["hail"] and c["level"] >= gate]
    ctl = [c for c in cases if not c["hail"] and c["level"] >= gate]
    day_hit = sum(alerts(c, radius, count).any() for c in hail)
    day_fa = sum(alerts(c, radius, count).any() for c in ctl)
    timed = [c for c in hail if c["hail_min"] is not None]
    before = [c for c in timed if alerts(c, radius, count)[(ticks >= c["hail_min"] - BEFORE) & (ticks <= c["hail_min"])].any()]
    hours_ctl = [alerts(c, radius, count).sum() * STEP / 60 for c in ctl]
    return {"hail_days": len(hail), "ctl_days": len(ctl), "day_hit": day_hit, "day_fa": day_fa,
            "timed": len(timed), "before": len(before), "ctl_hours_median": float(np.median(hours_ctl)) if hours_ctl else 0,
            "ctl_hours_mean": float(np.mean(hours_ctl)) if hours_ctl else 0}


n_hail = sum(c["hail"] for c in cases)
print(f"{len(cases)} días con el motor en \"Algunas chances\" o más ({n_hail} con granizo, {len(cases) - n_hail} sin granizo); "
      f"datos de {DELAY} min de demora\n")
print("Regla (radio, rayos)      días de granizo con aviso   días sin granizo con aviso   granizadas con hora: aviso en las 2 h previas   horas de aviso en días sin granizo (mediana)")
for r in RADII:
    for n in COUNTS:
        s = summary(r, n)
        mark = "  ← la de la app" if (r, n) == RULE else ""
        print(f"  ≤{r:2d} km, ≥{n:3d} rayos      {s['day_hit']:2d}/{s['hail_days']} ({s['day_hit'] / s['hail_days']:4.0%})"
              f"              {s['day_fa']:2d}/{s['ctl_days']} ({s['day_fa'] / s['ctl_days']:4.0%})"
              f"                 {s['before']:2d}/{s['timed']}"
              f"                                     {s['ctl_hours_median']:.1f}{mark}")
s = summary(*RULE, gate=2)
print(f"\nCon \"Chances reales\" en vez de \"Algunas chances\": días de granizo {s['day_hit']}/{s['hail_days']}, "
      f"sin granizo {s['day_fa']}/{s['ctl_days']}, con hora {s['before']}/{s['timed']}")

print("\nGranizadas con hora (regla de la app): primer aviso antes del granizo")
leads = []
for c in [c for c in cases if c["hail_min"] is not None]:
    a = alerts(c, *RULE)
    win = (ticks >= c["hail_min"] - BEFORE) & (ticks <= c["hail_min"])
    first = ticks[win][a[win]]
    leads.append(c["hail_min"] - first[0] if len(first) else None)
    print(f"  {c['e']['date']} {c['e']['localTime']} {c['e']['place'][:30]:30s} motor {c['level']}  "
          + (f"desde {c['hail_min'] - first[0]} min antes" if len(first) else "no saltó antes"))
early = sorted(x for x in leads if x is not None and x >= 10)
print(f"  → prendido al llegar el granizo: {sum(x is not None for x in leads)}/{len(leads)}; con ≥ 10 min de anticipación: "
      f"{len(early)}/{len(leads)} (mediana {np.median(early):.0f} min)" if early else "")
print("\nDías sin granizo con aviso (regla de la app): horas de aviso")
for c in [c for c in cases if not c["hail"]]:
    a = alerts(c, *RULE)
    print(f"  {c['e']['date']} {c['e']['place'][:30]:30s} motor {c['level']}  "
          + (f"{a.sum() * STEP / 60:.1f} h, de {ticks[a][0] // 60:02d}:{ticks[a][0] % 60:02d} a {ticks[a][-1] // 60:02d}:{ticks[a][-1] % 60:02d}" if a.any() else "no saltó"))
