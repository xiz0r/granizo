"""La app de hoy contra la app con el aviso "Ahora", con la misma vara: ¿cuánto mejora el acierto?

La app de hoy dice si hay condiciones de granizo en la ventana (nivel) y en qué horas (tira de horas: ambiente al menos
"supportive" en la zona, sin pasar del nivel). El PR agrega "cubrilo ahora": nivel "Algunas chances" o más y ≥ 3 rayos
a ≤ 20 km en la media hora de datos (20 min de demora). Tres preguntas:

1. Por día: ¿avisa los días de granizo y no los de tormenta sin granizo? (todos los casos con nivel del motor)
2. Por hora: en los días con "Algunas chances" o más, ¿cuántas horas marca cada uno y cubre la hora del granizo?
3. Pronósticos reales (registro_rayos.py): ¿en cuántas ventanas con "Algunas chances" la tormenta no llega?
4. Con el pronóstico real del día anterior (horas_motor_real.ts, casos de 2026): horas que marca la tira contra el aviso.

La tira de las preguntas 1 y 2 sale del archivo histórico (casi un pronóstico perfecto): es la mejor tira posible.
Intervalos: bootstrap de casos (95%). Lee horas.json (horas_motor.ts) y los rayos de glm_days.py. Sin red.
Uso: python3 comparar_app.py
"""
import csv
import json

import numpy as np

from motor import ROOT, all_cases, engine_level

HOURS = json.loads((ROOT / ".cache/research-nowcast/horas.json").read_text())
GLM = ROOT / ".cache/research-nowcast/glm-days"
RADIUS, COUNT, DELAY, W = 20, 3, 20, 30
TICKS = np.arange(0, 24 * 60 + 1, 10)
rng = np.random.default_rng(1)


def alert_ticks(cid):
    t = np.sort([float(r["min"]) for r in csv.DictReader(open(GLM / f"{cid}.csv")) if float(r["km"]) <= RADIUS])
    return (np.searchsorted(t, TICKS - DELAY) - np.searchsorted(t, TICKS - DELAY - W)) >= COUNT


cases = []
for cid, h in HOURS.items():
    e = all_cases[cid]
    level = engine_level(cid)
    if level is None or (e["type"] == "hail" and e["damaging"] is False):
        continue
    c = {"id": cid, "hail": e["type"] == "hail", "level": level, "uy": not cid.startswith("metar-"), "t": None}
    if e["localTime"]:
        hh, mm = map(int, e["localTime"].split(":"))
        c["t"] = hh * 60 + mm - (30 if c["uy"] and c["hail"] and "hora previa" in e["evidence"] else 0)
    day = [k for k in sorted(h["hours"]) if k[:10] == e["date"]]
    c["strip"] = {int(k[11:13]): h["hours"][k] != "weak" for k in day}  # horas de la tira, solo del día del caso
    if level >= 1:
        a = alert_ticks(cid)
        c["alert_day"] = bool(a.any())
        c["alert"] = {hr: bool(a[(TICKS >= hr * 60) & (TICKS < hr * 60 + 60)].any()) for hr in c["strip"]}
        if c["t"] is not None:
            c["alert_at"] = bool(a[(TICKS >= c["t"] - 60) & (TICKS <= c["t"])].any())
            c["alert_early"] = bool(a[(TICKS >= c["t"] - 120) & (TICKS <= c["t"] - 10)].any())
            th = c["t"] // 60
            c["strip_at"] = bool(c["strip"].get(th) or c["strip"].get(th - 1)) if th in c["strip"] else None
    else:
        c["alert_day"] = False
    cases.append(c)


def rates(sub, pred):
    y = np.array([c["hail"] for c in sub])
    p = np.array([pred(c) for c in sub])
    return p[y].mean(), p[~y].mean(), p[y].sum(), y.sum(), p[~y].sum(), (~y).sum()


def boot(sub, f, n=4000):
    idx = np.arange(len(sub))
    hail = idx[[c["hail"] for c in sub]]
    ctl = idx[[not c["hail"] for c in sub]]
    vals = []
    for _ in range(n):
        s = [sub[i] for i in np.r_[rng.choice(hail, len(hail)), rng.choice(ctl, len(ctl))]]
        vals.append(f(s))
    return np.percentile(vals, [2.5, 97.5])


def tss(sub, pred):
    a, b, *_ = rates(sub, pred)
    return a - b


watch = lambda c: c["level"] >= 1
protect = lambda c: c["level"] >= 2
alert = lambda c: c["alert_day"]

print("1. POR DÍA (¿avisó en algún momento del día?)")
for name, sub in (("Uruguay", [c for c in cases if c["uy"]]), ("Sur de Brasil", [c for c in cases if not c["uy"]]), ("Todos", cases)):
    print(f"  {name}: {sum(c['hail'] for c in sub)} días con granizo, {sum(not c['hail'] for c in sub)} días de tormenta sin granizo")
    for label, f in (('hoy, "Algunas chances" o más', watch), ('hoy, "Chances reales"', protect), ('PR, "cubrilo ahora"', alert)):
        pod, pofd, k, n, j, m = rates(sub, f)
        print(f"    {label:30s} detecta {k:2d}/{n} ({pod:4.0%})  falsas alarmas {j:2d}/{m} ({pofd:4.0%})  TSS {pod - pofd:+.2f}")
    lo, hi = boot(sub, lambda s: tss(s, alert) - tss(s, watch))
    print(f"    diferencia de TSS, PR − \"Algunas chances\": {tss(sub, alert) - tss(sub, watch):+.2f} (95%: {lo:+.2f} a {hi:+.2f})")

flagged = [c for c in cases if c["level"] >= 1]
print(f"\n2. POR HORA, en los {len(flagged)} días con \"Algunas chances\" o más "
      f"({sum(c['hail'] for c in flagged)} con granizo, {sum(not c['hail'] for c in flagged)} sin granizo)")
for name, key in (("tira de horas de hoy", "strip"), ("PR, \"cubrilo ahora\"", "alert")):
    ctl = [sum(c[key].values()) for c in flagged if not c["hail"]]
    hail = [sum(c[key].values()) for c in flagged if c["hail"]]
    print(f"  {name:22s} horas marcadas por día sin granizo: mediana {np.median(ctl):4.1f} (media {np.mean(ctl):4.1f}); "
          f"por día con granizo: mediana {np.median(hail):4.1f}")
timed = [c for c in flagged if c["hail"] and c["t"] is not None and c.get("strip_at") is not None]
print(f"  Granizadas con hora ({len(timed)}): la tira marcaba esa hora o la anterior en {sum(c['strip_at'] for c in timed)}; "
      f"el aviso estaba prendido en la hora previa en {sum(c['alert_at'] for c in timed)} "
      f"(con ≥ 10 min de anticipación en {sum(c['alert_early'] for c in timed)})")
tot_strip = sum(sum(c["strip"].values()) for c in flagged)
tot_alert = sum(sum(c["alert"].values()) for c in flagged)
print(f"  Total de horas marcadas en esos {len(flagged)} días: tira {tot_strip}, aviso {tot_alert} "
      f"({tot_alert / tot_strip:.0%} de las de la tira)")
ratio = boot(flagged, lambda s: sum(sum(c["alert"].values()) for c in s) / max(1, sum(sum(c["strip"].values()) for c in s)))
print(f"    (95%: {ratio[0]:.0%} a {ratio[1]:.0%})")

print("\n3. PRONÓSTICOS REALES GUARDADOS (registro_rayos.py): ventanas de 12 h con \"Algunas chances\": 89; con aviso: 49 (55%).")
k, n = 49, 89
z = 1.96
p = k / n
centre = (p + z * z / (2 * n)) / (1 + z * z / n)
half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
print(f"  Sin aviso: {n - k} de {n} ({1 - p:.0%}; 95%: {1 - centre - half:.0%} a {1 - centre + half:.0%}). Si el aviso conserva el "
      f"{rates(cases, alert)[0] / rates(cases, watch)[0]:.0%} de las granizadas que marca \"Algunas chances\" (punto 1), la chance de que "
      f"granice cuando la app pide actuar se multiplica por ~{(rates(cases, alert)[0] / rates(cases, watch)[0]) / p:.1f}.")

REAL = json.loads((ROOT / ".cache/research-nowcast/horas-real.json").read_text())
print("\n4. PRONÓSTICO REAL DEL DÍA ANTERIOR (2026), días con \"Algunas chances\" o más y rayos bajados")
real = []
for cid, r in REAL.items():
    e = all_cases[cid]
    if r["level"] == "calm" or (e["type"] == "hail" and e["damaging"] is False) or not (GLM / f"{cid}.csv").exists():
        continue
    strip = {int(k[11:13]): r["hours"][k] != "weak" for k in sorted(r["hours"]) if k[:10] == e["date"]}
    a = alert_ticks(cid)
    real.append((e["type"] == "hail", sum(strip.values()), sum(a[(TICKS >= hr * 60) & (TICKS < hr * 60 + 60)].any() for hr in strip),
                 bool(a.any())))
for hail, name in ((True, "con granizo"), (False, "sin granizo")):
    sub = [x for x in real if x[0] == hail]
    print(f"  {len(sub)} días {name}: horas de la tira {sum(x[1] for x in sub)} (mediana {np.median([x[1] for x in sub]):.0f}), "
          f"horas de aviso {sum(x[2] for x in sub)} (mediana {np.median([x[2] for x in sub]):.0f}); días con aviso {sum(x[3] for x in sub)}")
