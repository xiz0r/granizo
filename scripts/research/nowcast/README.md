# Aviso "Ahora": qué se probó y qué quedó

Scripts que respaldan el aviso "Ahora" (`NOWCAST` en `src/engine/config.ts`): el motor ve ambiente de granizo para el día **y** hay una tormenta eléctrica cerca. También los de las fuentes que se probaron y quedaron afuera del JSON (lluvia por satélite y radar). Necesitan Python con numpy y h5py (y Pillow para el radar). Los resultados de la corrida del 2026-10-23 están en `resultados/`.

## Casos

- `data/events.json`: los 76 casos uruguayos con hora (13 granizadas y 63 tormentas sin granizo; sin granizo chico). Con ellos se eligieron el radio (20 km) y la cantidad de rayos (3).
- `casos_metar.json` (lo arma `casos_metar.py`): **prueba independiente**. 16 granizadas reportadas por METAR (GR) en aeropuertos del sur de Brasil y en Melo, y 64 días de tormenta (TS) sin granizo en los mismos aeropuertos, emparejados por época del año. La regla no se tocó para esta prueba. El nivel del motor lo calcula `niveles_metar.ts` con el motor actual (`niveles_metar.json`). Faltan 7 casos de 2026 porque se agotó el cupo diario de Open-Meteo, y los anteriores a 2021-03 no tienen archivo.
- `data/forecast-log/runs/`: los pronósticos reales guardados desde abril de 2026, sin elegir casos.

Solo cuenta lo que la app sabría **antes** del granizo: los rayos de la media hora que termina 20 minutos antes (el JSON se arma cada 10 minutos y llega con demora).

## Resultados

| Prueba | Script | Resultado |
|---|---|---|
| Media hora antes, Uruguay | `evaluar.py` | 8 de 13 granizadas, 7 de 63 tormentas sin granizo |
| Media hora antes, sur de Brasil (independiente) | `prueba_metar.py` | 4 de 9 granizadas, 6 de 44 tormentas sin granizo |
| Todo el día, 85 días de tormenta con "Algunas chances" o más | `evaluar_dia.py` | Saltó en 45 de 46 días con granizo y en 36 de 39 sin granizo (mediana 3 h prendido). Prendido al llegar el granizo en 12 de 15; con ≥ 10 min de anticipación en 8 (mediana 45 min) |
| Pronósticos reales guardados (abril–octubre de 2026) | `registro_rayos.py` | Saltó en 49 de 89 ventanas de 12 h con "Algunas chances" (55%) y en 15 de 21 con "Chances reales" (71%) |

**Lectura.** Los rayos cerca no distinguen una tormenta con granizo de una sin granizo: en los días en que la tormenta pasa por el lugar, el aviso salta casi siempre. Lo que aporta es **cuándo**: en un día marcado por el motor, avisa cuando la tormenta está a menos de 20 km, y en casi la mitad de los días con "Algunas chances" la tormenta nunca llega y el aviso no salta. La probabilidad de granizo la sigue dando el motor.

Variantes cercanas (25–30 km, 10 rayos, 30–40 km con más rayos) dan casi lo mismo; no hay razón para moverse de 20 km y 3 rayos.

## Lo que se probó y quedó afuera

- **Lluvia estimada por satélite (GOES ABI RRQPE)**, `rrqpe_cases.py` y `evaluar_lluvia.py`, en 145 casos con hora. Sola separa poco (AUC 0,67), y una vez que el aviso de rayos saltó no suma nada (AUC 0,47).
- **Radar de REDEMET (Santiago y Canguçu, Brasil)**, `redemet_dbz.py`, `radar_days.py` y `evaluar_radar.py`.
  - Las imágenes se pasaron a dBZ: la escala es una rampa de 10 colores cada 5 dBZ, y la leyenda del sitio y Marshall-Palmer la confirman.
  - Archivo desde 2018 con huecos. Solo el maxcappi (máximo de la columna) tiene archivo completo; los CAPPI de 3–10 km traen 1–7 imágenes por día.
  - Con los primeros 30 casos uruguayos parecía muy bueno: ≥ 50 dBZ a ≤ 20 km en 17 de 19 días de granizo contra 1 de 11 sin granizo. Con los controles de Brasil (30 días con granizo, 62 sin granizo) bajó a 24 de 30 contra 21 de 62. Con el motor en "Algunas chances" o más, distingue poco (AUC 0,75).
  - Con la demora real (~10 min de REDEMET más la de la app), ve el núcleo antes del granizo en 5 de 15 casos: casi siempre llega tarde.
  - Además cubre solo el norte y el este, tiene cortes de horas, y el de Santiago se ve mucho más débil en 2026.

## Cómo repetirlo

```bash
cd scripts/research/nowcast
python3 glm_cases.py                                          # rayos t−120…t+30 de los casos de events.json → .cache/research-nowcast/glm
python3 casos_metar.py                                        # METAR de Iowa Environmental Mesonet → casos_metar.json
node niveles_metar.ts                                         # nivel del motor de esos casos (Open-Meteo) → niveles_metar.json
python3 glm_cases.py ../../../.cache/research-nowcast/glm casos_metar.json
python3 glm_days.py                                           # rayos del día completo (casos con "Algunas chances" o más)
python3 glm_days.py ../../../.cache/research-nowcast/glm-days 48 casos_metar.json
python3 evaluar.py && python3 prueba_metar.py && python3 evaluar_dia.py && python3 registro_rayos.py
python3 rrqpe_cases.py && python3 evaluar_lluvia.py           # lluvia por satélite
REDEMET_API_KEY=... python3 radar_days.py                     # radar (necesita la clave gratuita de REDEMET)
REDEMET_API_KEY=... python3 radar_days.py ../../../.cache/research-nowcast/radar casos_metar.json
python3 evaluar_radar.py
```

Las descargas de rayos son pesadas: ~1 GB y 2–5 minutos por día completo. Todo queda en `.cache/research-nowcast/`, fuera del repo.
