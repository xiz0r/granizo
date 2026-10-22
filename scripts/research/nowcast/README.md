# Aviso "Ahora": calibración con rayos

Scripts que respaldan el aviso "Ahora" (`NOWCAST` en `src/engine/config.ts`): el motor ve ambiente de granizo para el día **y** hay una tormenta eléctrica activa cerca. Necesitan Python con numpy y h5py.

```bash
python3 scripts/research/nowcast/glm_cases.py   # rayos del GOES por caso con hora → .cache/research-nowcast/glm (~40 min, ~8 GB)
python3 scripts/research/nowcast/evaluar.py     # motor + rayos antes del granizo, validación cruzada → resultados/evaluacion.txt
python3 scripts/research/nowcast/evaluar.py .cache/research-nowcast/glm 60   # peor caso para los METAR "en la hora previa"
```

- Casos: los 76 con hora de `data/events.json` (13 granizadas y 63 tormentas sin granizo; sin granizo chico).
- Solo cuenta lo que se sabía **antes** del granizo: los rayos de la media hora que termina 10 o 20 minutos antes, como los ve la app (el JSON se arma cada 10 minutos y llega con demora).
- El nivel del motor sale de `reports/backtest.csv` y `reports/ecmwf-eval.json` (casi análisis, no pronóstico real).
- Resultado de la corrida del 2026-10-22 en `resultados/evaluacion.txt`.
