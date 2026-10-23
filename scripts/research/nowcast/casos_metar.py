"""Más casos con hora exacta para el aviso "Ahora": granizo (GR) reportado por METAR en aeropuertos del sur de Brasil y
en Melo, y días de tormenta (TS) sin granizo en esos mismos aeropuertos como controles.

Por qué: data/events.json tiene solo 13 granizadas con hora. El aviso depende de rayos y radar alrededor del punto, que
se comportan igual a un lado y al otro de la frontera (misma región, mismo tipo de tormentas), y estos aeropuertos están
cerca de los radares de Santiago y Canguçu. Los aeropuertos uruguayos con METAR ya están en events.json.

- Granizo: GR en el tiempo presente, o REGR ("en la hora previa", se corre 30 min). GS (granizo chico) no cuenta, igual
  que en events.json. Un caso por aeropuerto y día local (UTC−3); la hora es la del primer reporte.
- Controles: días con tormenta en el aeropuerto (≥ 2 reportes con TS o uno con +TS), sin GR/GS ese día ni el anterior o
  el siguiente en ningún aeropuerto de la lista ni en events.json. Hasta 4 por granizada, del mismo aeropuerto si se
  puede, a ≤ 45 días del año de distancia; la hora es la del primer reporte con TS fuerte (o el primero con TS).

Descarga los METAR de Iowa Environmental Mesonet (sin cuenta) a .cache/research-nowcast/metar/ y escribe
casos_metar.json con el mismo formato que data/events.json. Uso: python3 casos_metar.py
"""
import csv
import json
import re
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

from motor import ROOT

STATIONS = {  # IEM: BR__ASOS y UY__ASOS
    "SBBG": ("Bagé (RS)", -31.35, -54.1167), "SBNM": ("Santo Ângelo (RS)", -28.2817, -54.1691),
    "SBPK": ("Pelotas (RS)", -31.7833, -52.4167), "SBSM": ("Santa Maria (RS)", -29.7114, -53.6882),
    "SBPA": ("Porto Alegre (RS)", -29.9944, -51.1714), "SBCO": ("Canoas (RS)", -29.9455, -51.1439),
    "SBUG": ("Uruguaiana (RS)", -29.7822, -57.0382), "SUMO": ("Melo (aeropuerto)", -32.337, -54.2167),
}
FROM, TO = date(2018, 1, 1), date(2026, 10, 22)
CACHE = ROOT / ".cache/research-nowcast/metar"
CACHE.mkdir(parents=True, exist_ok=True)
WX = re.compile(r"(\+|-|VC|RE)?[A-Z]{2,10}")


def metars(sid):
    path = CACHE / f"{sid}.csv"
    if not path.exists():
        url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=" + sid + "&data=metar"
               f"&year1={FROM.year}&month1={FROM.month}&day1={FROM.day}&year2={TO.year}&month2={TO.month}&day2={TO.day}"
               "&tz=Etc/UTC&format=onlycomma&latlon=no&missing=M&trace=T&direct=no&report_type=3&report_type=4")
        path.write_bytes(urllib.request.urlopen(url, timeout=300).read())
    for r in csv.DictReader(open(path)):
        body = re.split(r" (RMK|TEMPO|BECMG|NOSIG)( |$)", r["metar"] or "")[0]
        wx = [t for t in body.split()[2:] if WX.fullmatch(t) and not t.startswith(("CAVOK", "NOSIG", "NSC", "SKC", "CLR", "AUTO",
                                                                                 "COR", "FEW", "SCT", "BKN", "OVC", "NCD"))]
        yield datetime.fromisoformat(r["valid"]), " ".join(wx), r["metar"]


hail, ts_days, gr_days = {}, defaultdict(lambda: {"ts": 0, "heavy": None, "first": None}), set()
for sid in STATIONS:
    for t, wx, raw in metars(sid):
        local = t - timedelta(hours=3)
        day = local.date()
        if re.search(r"GR|GS", wx):
            gr_days.add(day)
        if re.search(r"(^| )(\+|-)?[A-Z]*GR", wx) and "GS" not in wx.replace("GR", ""):
            recent = all(w.startswith("RE") for w in wx.split() if "GR" in w)
            when = local - timedelta(minutes=30) if recent else local
            key = (sid, when.date())
            # Manda el primer reporte de granizo en el momento; "en la hora previa" solo si no hay ninguno.
            old = hail.get(key)
            if old is None or (old[2] and not recent) or (old[2] == recent and when < old[0]):
                hail[key] = (when, raw, recent)
        if re.search(r"(^| )(\+|-)?TS", wx):
            d = ts_days[(sid, day)]
            d["ts"] += 1
            d["first"] = d["first"] or local
            if "+TS" in wx and d["heavy"] is None:
                d["heavy"] = local
events = json.loads((ROOT / "data/events.json").read_text())
gr_days |= {date.fromisoformat(e["date"]) for e in events if e["type"] == "hail"}


def near_hail(day):
    return any(day + timedelta(days=k) in gr_days for k in (-1, 0, 1))


def doy_gap(a, b):
    x = abs(a.timetuple().tm_yday - b.timetuple().tm_yday)
    return min(x, 365 - x)


known = {(e["date"], e["localTime"]) for e in events}
cases = []
for (sid, day), (when, raw, recent) in sorted(hail.items(), key=lambda kv: kv[1][0]):
    if (str(day), f"{when:%H:%M}") in known:
        continue
    name, lat, lon = STATIONS[sid]
    cases.append({"id": f"metar-{day}-{sid.lower()}", "type": "hail", "date": str(day), "localTime": f"{when:%H:%M}",
                  "place": name, "lat": lat, "lon": lon, "hailSizeCm": None, "damaging": None, "station": sid,
                  "evidence": f"METAR {raw}" + (" (granizo en la hora previa)" if recent else "")})
pool = [(sid, day, d) for (sid, day), d in ts_days.items()
        if (d["ts"] >= 2 or d["heavy"]) and not near_hail(day) and FROM <= day <= TO]
used, per_date = set(), defaultdict(int)
for h in [c for c in cases if c["type"] == "hail"]:
    hd = date.fromisoformat(h["date"])
    options = sorted((c for c in pool if (c[0], c[1]) not in used and per_date[c[1]] < 2 and doy_gap(hd, c[1]) <= 45),
                     key=lambda c: (c[0] != h["station"], doy_gap(hd, c[1]), abs((c[1] - hd).days)))
    for sid, day, d in options[:4]:
        used.add((sid, day))
        per_date[day] += 1
        when = d["heavy"] or d["first"]
        name, lat, lon = STATIONS[sid]
        cases.append({"id": f"metar-ctl-{day}-{sid.lower()}", "type": "control", "date": str(day), "localTime": f"{when:%H:%M}",
                      "place": name, "lat": lat, "lon": lon, "hailSizeCm": None, "damaging": None, "station": sid,
                      "evidence": f"METAR {sid}: tormenta (TS) en {d['ts']} reportes" + (", con +TS" if d["heavy"] else "") +
                                  "; sin GR/GS ese día ni el anterior o el siguiente en estos aeropuertos ni en events.json"})
out = ROOT / "scripts/research/nowcast/casos_metar.json"
out.write_text(json.dumps(sorted(cases, key=lambda c: (c["date"], c["id"])), ensure_ascii=False, indent=1) + "\n")
print(f"{sum(c['type'] == 'hail' for c in cases)} granizadas y {sum(c['type'] == 'control' for c in cases)} controles → {out}")
for c in cases:
    if c["type"] == "hail":
        print(" ", c["date"], c["localTime"], c["place"], "|", c["evidence"][:90])
