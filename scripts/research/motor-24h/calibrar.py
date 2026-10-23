"""Motor de 24 h: v0.2.1 contra los cambios candidatos, con los ingredientes por punto-hora de exportar.ts.

Casos: granizo (dañino o sin dato de tamaño) contra días de tormenta sin granizo; sin granizo chico (como el backtest).
Reglas, por modelo y combinadas para GFS + ECMWF:
  v0.2.1          el motor actual (gradiente ≥ 6,5 y WMAXSHEAR ≥ 1200 + tormentas en algún lugar de la ventana →
                  "Chances reales"; ≥ 900 → "Algunas chances")
  disparo ±3 h    igual, pero las tormentas del modelo tienen que caer a ±3 h de un punto-hora con ambiente fuerte
  puntaje         logística sobre el percentil 90 de ln(gradiente·WMAXSHEAR) en los punto-horas del caso (el mejor
                  predictor de la investigación v0.3), por modelo y promediada; los niveles son los umbrales que dan las
                  MISMAS falsas alarmas que v0.2.1 en entrenamiento ("¿con las mismas falsas alarmas, más granizo?")
Validación: dejando un año afuera (ajuste y umbrales sin ese año). Pronóstico real: entrenado con el histórico sin el año
del caso y aplicado a la corrida del día anterior.
Uso: python3 calibrar.py <historical.csv o -> <single_run.csv o ->
"""
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

EVENTS = {e["id"]: e for e in json.load(open(Path(__file__).resolve().parents[3] / "data/events.json"))}
MODELS = ("gfs_seamless", "ecmwf_ifs025")


def label(e):
    if e["type"] == "control":
        return 0
    return None if e["damaging"] is False else 1


def load(path):
    if path == "-":
        return {}
    ph = defaultdict(list)
    for r in csv.DictReader(open(path)):
        if r["lapse"] == "" or r["wmax"] == "":
            continue
        ph[(r["id"], r["model"])].append((r["time"], float(r["lapse"]), float(r["wmax"]), float(r["showers"] or 0), float(r["precip"] or 0)))
    return ph


def case_features(rows):
    t = np.array([np.datetime64(x[0]) for x in rows])
    lapse = np.array([x[1] for x in rows]); wmax = np.array([x[2] for x in rows])
    trig = (np.array([x[3] for x in rows]) >= 0.5) | (np.array([x[4] for x in rows]) >= 2.0)
    strong = (lapse >= 6.5) & (wmax >= 1200)
    supp = (lapse >= 6.5) & (wmax >= 900)
    any_trig = trig.any()
    col = False
    if strong.any() and trig.any():
        ts, tt = t[strong], t[trig]
        col = bool((np.abs(ts[:, None] - tt[None, :]) <= np.timedelta64(3, "h")).any())
    lvl = 2 if strong.any() and any_trig else 1 if (strong.any() or supp.any()) else 0
    lvl_col = 2 if col else 1 if (strong.any() or supp.any()) else 0
    lxw = np.log(np.clip(lapse, 0.1, None) * np.clip(wmax, 1, None))
    return {"lvl": lvl, "lvl_col": lvl_col, "x": float(np.quantile(lxw, 0.9)), "trig": bool(any_trig)}


def combine(a, b):
    """Regla "los dos modelos" de v0.2.1."""
    if a is None or b is None:
        return a if b is None else b
    return 2 if a == 2 and b == 2 else 1 if (2 in (a, b) or (a >= 1 and b >= 1)) else 0


def build(ph):
    cases = {}
    for (cid, model), rows in ph.items():
        y = label(EVENTS[cid])
        if y is None:
            continue
        c = cases.setdefault(cid, {"id": cid, "y": y, "year": EVENTS[cid]["date"][:4], "date": EVENTS[cid]["date"],
                                   "warm": EVENTS[cid]["date"][5:7] in ("10", "11", "12", "01", "02", "03")})
        c[model] = case_features(rows)
    return list(cases.values())


def fit_logit(x, y, l2=0.1):
    """Logística de una variable (Newton, con un poco de ridge)."""
    X = np.c_[np.ones(len(x)), x]
    w = np.zeros(2)
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + l2 * np.r_[0, w[1]]
        H = X.T @ (X * (p * (1 - p))[:, None]) + l2 * np.diag([0, 1])
        w -= np.linalg.solve(H, g)
    return w


def prob(w, x):
    return 1 / (1 + np.exp(-(w[0] + w[1] * x)))


def score_cases(train, test):
    """Logística por modelo en entrenamiento; para cada caso de prueba, el promedio de los modelos que tiene."""
    ws = {}
    for m in MODELS:
        tr = [c for c in train if m in c]
        if len(tr) > 10:
            ws[m] = fit_logit(np.array([c[m]["x"] for c in tr]), np.array([c["y"] for c in tr]))
    out = []
    for c in test:
        ps = [prob(ws[m], c[m]["x"]) for m in MODELS if m in c and m in ws]
        out.append(np.mean(ps) if ps else np.nan)
    return np.array(out)


def v021(cases, key="lvl"):
    return np.array([combine(c["gfs_seamless"][key] if "gfs_seamless" in c else None,
                             c["ecmwf_ifs025"][key] if "ecmwf_ifs025" in c else None) for c in cases])


def thresholds_matching(p, y, lv):
    """Umbrales del puntaje con las mismas falsas alarmas que "Chances reales" y "Algunas chances o más" de v0.2.1."""
    neg = np.sort(p[y == 0])[::-1]
    out = []
    for k in (2, 1):
        fa = (lv[y == 0] >= k).mean()
        n = int(round(fa * len(neg)))
        out.append(neg[n] + 1e-9 if n < len(neg) else -np.inf)  # alarma = p > umbral: quedan n controles arriba
    return out  # [t_protect, t_watch]


def report(name, y, pred):
    pod, pofd = pred[y == 1].mean(), pred[y == 0].mean()
    print(f"    {name:42s} detecta {pred[y == 1].sum():3d}/{(y == 1).sum()} ({pod:4.0%})  falsas {pred[y == 0].sum():3d}/{(y == 0).sum()} ({pofd:4.0%})  TSS {pod - pofd:+.2f}")


def auc(p, y):
    a, b = p[y == 1], p[y == 0]
    return np.mean([(x > b).mean() + 0.5 * (x == b).mean() for x in a])


def section(title, cases, train_pool=None):
    y = np.array([c["y"] for c in cases])
    print(f"\n=== {title}: {len(cases)} casos ({y.sum()} granizo, {(y == 0).sum()} controles) ===")
    lv, lc = v021(cases), v021(cases, "lvl_col")
    # puntaje dejando un año afuera
    p = np.full(len(cases), np.nan)
    tp = np.zeros(len(cases)); tw = np.zeros(len(cases))
    pool = train_pool if train_pool is not None else cases
    for yr in sorted({c["year"] for c in cases}):
        tr = [c for c in pool if c["year"] != yr]
        te_idx = [i for i, c in enumerate(cases) if c["year"] == yr]
        ytr = np.array([c["y"] for c in tr])
        if len(tr) < 20 or ytr.sum() == 0 or (ytr == 0).sum() == 0:
            continue
        ptr = score_cases(tr, tr)
        t_prot, t_watch = thresholds_matching(ptr, ytr, v021(tr))
        p[te_idx] = score_cases(tr, [cases[i] for i in te_idx])
        tp[te_idx], tw[te_idx] = t_prot, t_watch
    for k, name in ((2, "Chances reales"), (1, "Algunas chances o más")):
        print(f"  {name}:")
        report("v0.2.1 (actual)", y, lv >= k)
        report("v0.2.1 con disparo a ±3 h del ambiente", y, lc >= k)
        if not np.isnan(p).all():
            report("puntaje continuo, mismas falsas alarmas", y, p > (tp if k == 2 else tw))
    ok = ~np.isnan(p)
    if not ok.any():
        ok = np.ones(len(p), bool); p = lv.astype(float)
    print(f"  AUC: v0.2.1 (3 niveles) {auc(lv[ok].astype(float), y[ok]):.2f} · puntaje continuo {auc(p[ok], y[ok]):.2f}")
    w = np.array([c["warm"] for c in cases])
    for s, nm in ((False, "fría"), (True, "cálida")):
        m = (w == s) & ok
        if (y[m] == 1).sum() and (y[m] == 0).sum():
            print(f"  estación {nm}: n={(y[m] == 1).sum()}/{(y[m] == 0).sum()}  AUC v0.2.1 {auc(lv[m].astype(float), y[m]):.2f} · puntaje {auc(p[m], y[m]):.2f}"
                  f" · Chances reales v0.2.1 {(lv[m] >= 2)[y[m] == 1].mean():.0%}/{(lv[m] >= 2)[y[m] == 0].mean():.0%}")


hist = build(load(sys.argv[1]))
runs = build(load(sys.argv[2]))
if hist:
    section("Archivo histórico (casi análisis), validación dejando un año afuera", hist)
if runs:
    section("Pronóstico real del día anterior (12 UTC), reglas entrenadas " + ("con el histórico sin el año del caso" if hist else "en la misma muestra sin el año"),
            runs, train_pool=hist or None)
    by_model = defaultdict(list)
    for c in runs:
        for m in MODELS:
            if m in c:
                by_model[m].append((c["y"], c[m]["lvl"]))
    for m, v in by_model.items():
        yy = np.array([a for a, _ in v]); ll = np.array([b for _, b in v])
        print(f"  solo {m}: Chances reales {(ll >= 2)[yy == 1].sum()}/{(yy == 1).sum()} · {(ll >= 2)[yy == 0].sum()}/{(yy == 0).sum()} falsas"
              f" | Algunas+ {(ll >= 1)[yy == 1].sum()}/{(yy == 1).sum()} · {(ll >= 1)[yy == 0].sum()}/{(yy == 0).sum()}")
