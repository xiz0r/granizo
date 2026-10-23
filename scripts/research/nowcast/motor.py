"""Casos y nivel del motor v0.2.1 de cada uno, sin red.

- data/events.json: el nivel sale del pico guardado en reports/backtest.csv (v0.2.0, combinado) y reports/ecmwf-eval.json
  (cada modelo desde 2024-06). "Chances reales" no cambió; "Algunas chances" pide WMAXSHEAR ≥ 900 (o ambiente fuerte
  sin tormentas en el modelo); dos modelos con la regla "both".
- casos_metar.json (aeropuertos del sur de Brasil y Melo): el nivel lo calcula niveles_metar.ts con el motor actual;
  None si todavía no se calculó o si el caso es anterior al archivo de Open-Meteo (2021-03).
"""
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
events = {e["id"]: e for e in json.loads((ROOT / "data/events.json").read_text())}
backtest = {r["id"]: r for r in csv.DictReader(open(ROOT / "reports/backtest.csv"))}
by_model = json.loads((ROOT / "reports/ecmwf-eval.json").read_text())
HERE = Path(__file__).resolve().parent
metar = {e["id"]: e for e in json.loads((HERE / "casos_metar.json").read_text())} if (HERE / "casos_metar.json").exists() else {}
metar_levels = json.loads((HERE / "niveles_metar.json").read_text()) if (HERE / "niveles_metar.json").exists() else {}
all_cases = {**events, **metar}
num = lambda x: None if x in ("", "—", None) else float(x)


def model_level(level, env, lapse, wmax):
    if level == "protect":
        return 2
    if env == "strong" or (lapse is not None and wmax is not None and lapse >= 6.5 and wmax >= 900):
        return 1
    return 0


def engine_level(cid):
    if cid in metar:
        return {"calm": 0, "watch": 1, "protect": 2}.get(metar_levels.get(cid))
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
