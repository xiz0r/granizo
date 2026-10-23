"""¿El radar de REDEMET distingue granizo de tormenta sin granizo cerca del punto? ¿Suma al aviso de rayos?

Lee los recortes de radar_days.py (maxcappi de Santiago y Canguçu, en dBZ) de los casos de Uruguay (events.json) y del
sur de Brasil (casos_metar.json). Usa el radar que tenga al menos medio día de imágenes (si hay dos, el máximo).

- En el día: máximo de reflectividad a ≤ r km del punto en todo el día local. Dice si el radar "ve" el granizo.
- Antes del granizo (casos con hora): lo que vería la app con datos de 20 min (como los rayos) y las imágenes de REDEMET
  publicadas ~10 min después de tomadas: imágenes tomadas entre 60 y 30 min antes del granizo.

Uso: python3 evaluar_radar.py [carpeta=.cache/research-nowcast/radar]
"""
import csv
import sys
from pathlib import Path

import numpy as np

from motor import ROOT, all_cases, engine_level

DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache/research-nowcast/radar"
GLM = ROOT / ".cache/research-nowcast/glm"
MIN_FRAMES = 36  # medio día de imágenes cada 20 min
PRE = (-60, -30)  # minutos respecto del granizo
RADII, LEVELS = (10, 20, 30), (45, 50, 55, 60)


def near_max(d, radius, window=None):
    z = np.where(d["km"] <= radius, d["dbz"], np.nan)
    per_frame = np.nanmax(np.where(np.isnan(z), -1, z), axis=(1, 2))
    if window is not None:
        per_frame = per_frame[(d["utc"] >= window[0]) & (d["utc"] < window[1])]
    return float(per_frame.max()) if len(per_frame) else np.nan


cases = []
for cid, e in all_cases.items():
    files = {p.name.split(".")[1]: np.load(p) for p in DIR.glob(f"{cid}.*.maxcappi.npz")}
    if not files or (e["type"] == "hail" and e["damaging"] is False):
        continue
    ok = {a: d for a, d in files.items() if len(d["utc"]) >= MIN_FRAMES and d["dbz"].ndim == 3}
    t = None
    if e["localTime"]:
        hh, mm = map(int, e["localTime"].split(":"))
        t = hh * 60 + mm - (30 if not cid.startswith("metar-") and e["type"] == "hail" and "hora previa" in e["evidence"] else 0)
    c = {"id": cid, "e": e, "hail": e["type"] == "hail", "level": engine_level(cid), "t": t, "br": cid.startswith("metar-"),
         "radars": {a: float(d["range_km"]) for a, d in ok.items()}}
    for r in RADII:
        c[f"day{r}"] = max((near_max(d, r) for d in ok.values()), default=np.nan)
        c[f"pre{r}"] = max((near_max(d, r, (t + PRE[0], t + PRE[1])) for d in ok.values()), default=np.nan) if t is not None else np.nan
    if t is not None and (GLM / f"{cid}.csv").exists():
        end = (-30 if not c["br"] and c["hail"] and "hora previa" in e["evidence"] else 0) - 20
        c["flashes"] = sum(1 for x in csv.DictReader(open(GLM / f"{cid}.csv")) if end - 30 <= float(x["min"]) < end and float(x["km"]) <= 20)
    cases.append(c)

valid = [c for c in cases if c["radars"]]
print(f"{len(cases)} casos a ≤ 330 km de un radar; {len(valid)} con al menos medio día de imágenes "
      f"({sum(c['hail'] for c in valid)} con granizo, {sum(not c['hail'] for c in valid)} sin granizo)\n")


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    return np.mean([(p > neg).mean() + 0.5 * (p == neg).mean() for p in pos]) if len(pos) and len(neg) else np.nan


def block(title, sub, key):
    sub = [c for c in sub if not np.isnan(c[f"{key}20"])]
    y = np.array([c["hail"] for c in sub])
    if not y.any() or y.all():
        return
    print(f"{title}: {y.sum()} con granizo, {(~y).sum()} sin granizo")
    for r in RADII:
        v = np.array([c[f"{key}{r}"] for c in sub])
        cells = "   ".join(f"≥{lv}: {(v[y] >= lv).sum():2d}/{y.sum()} vs {(v[~y] >= lv).sum():2d}/{(~y).sum()}" for lv in LEVELS)
        print(f"  máx a ≤{r:2d} km   AUC {auc(v[y], v[~y]):.2f}   {cells}")


lv = lambda c: c["level"] is not None and c["level"] >= 1
for region, sel in (("Uruguay", lambda c: not c["br"]), ("Sur de Brasil", lambda c: c["br"]), ("Todos", lambda c: True)):
    block(f"{region}, en el día", [c for c in valid if sel(c)], "day")
    block(f"{region}, en el día, motor ≥ \"Algunas chances\"", [c for c in valid if sel(c) and lv(c)], "day")
    block(f"{region}, 60–30 min antes", [c for c in valid if sel(c)], "pre")
    print()

timed = [c for c in valid if "flashes" in c and not np.isnan(c["pre20"])]
y = np.array([c["hail"] for c in timed])
print(f"Casos con hora, radar y rayos: {y.sum()} con granizo, {(~y).sum()} sin granizo (datos de 20 min para los rayos)")
for name, f in (("≥3 rayos a ≤20 km", lambda c: c["flashes"] >= 3),
                ("radar ≥50 dBZ a ≤20 km", lambda c: c["pre20"] >= 50),
                ("radar ≥55 dBZ a ≤20 km", lambda c: c["pre20"] >= 55),
                ("rayos y radar ≥50", lambda c: c["flashes"] >= 3 and c["pre20"] >= 50),
                ("rayos o radar ≥50", lambda c: c["flashes"] >= 3 or c["pre20"] >= 50)):
    p = np.array([f(c) for c in timed])
    g = np.array([f(c) and lv(c) for c in timed])
    known = np.array([c["level"] is not None for c in timed])
    print(f"  {name:28s} solo: {p[y].sum():2d}/{y.sum()} vs {p[~y].sum():2d}/{(~y).sum()}"
          f"   con motor ≥ \"Algunas chances\": {g[y & known].sum():2d}/{(y & known).sum()} vs {g[~y & known].sum():2d}/{(~y & known).sum()}")



def radar_alert_ticks(c, radius, level, lag=30):
    """Aviso de radar en cada tick de 10 min del día: la última imagen tomada ≤ lag min antes (REDEMET tarda ~10 min
    en publicarla y la app ve datos de hasta 20 min) tiene ≥ level dBZ a ≤ radius km."""
    ticks = np.arange(0, 24 * 60 + 1, 10)
    on = np.zeros(len(ticks), bool)
    for d in (np.load(DIR / f"{c['id']}.{a}.maxcappi.npz") for a in c["radars"]):
        z = np.where(d["km"] <= radius, d["dbz"], np.nan)
        hit = np.nanmax(np.where(np.isnan(z), -1, z), axis=(1, 2)) >= level
        idx = np.searchsorted(d["utc"], ticks - lag, side="right") - 1
        on |= (idx >= 0) & hit[np.clip(idx, 0, None)] & (ticks - lag - d["utc"][np.clip(idx, 0, None)] <= 30)
    return ticks, on


print("\nAviso de radar a lo largo del día (como la app: imagen de hasta 30 min antes), motor sin mirar / con motor ≥ \"Algunas chances\":")
for radius, level in ((10, 50), (20, 45), (20, 50), (20, 55), (30, 50)):
    res = {}
    for gate in (False, True):
        sub = [c for c in valid if not gate or lv(c)]
        hail_day = [radar_alert_ticks(c, radius, level)[1].any() for c in sub if c["hail"]]
        ctl_day = [radar_alert_ticks(c, radius, level)[1].any() for c in sub if not c["hail"]]
        before = []
        for c in sub:
            if c["hail"] and c["t"] is not None:
                ticks, on = radar_alert_ticks(c, radius, level)
                before.append(on[(ticks >= c["t"] - 120) & (ticks <= c["t"])].any())
        res[gate] = (sum(hail_day), len(hail_day), sum(ctl_day), len(ctl_day), sum(before), len(before))
    a, b = res[False], res[True]
    print(f"  ≥{level} dBZ a ≤{radius} km: días de granizo {a[0]}/{a[1]}, sin granizo {a[2]}/{a[3]}, antes del granizo {a[4]}/{a[5]}"
          f"   |  con motor: {b[0]}/{b[1]}, {b[2]}/{b[3]}, antes {b[4]}/{b[5]}")

print("\nCasos (máx a ≤10/20 km en el día; 60–30 min antes a ≤20 km):")
for c in sorted(cases, key=lambda c: (not c["hail"], c["e"]["date"])):
    rad = ", ".join(f"{a} {c['radars'][a]:.0f} km" for a in c["radars"]) or "sin radar"
    pre = f"  antes {c['pre20']:3.0f}" if not np.isnan(c["pre20"]) else ""
    print(f"  {'GRANIZO' if c['hail'] else 'control'} {c['e']['date']} {c['e']['place'][:24]:24s} motor {'—' if c['level'] is None else c['level']}  "
          f"{c['day10']:4.0f} {c['day20']:4.0f} dBZ{pre}  [{rad}]")
