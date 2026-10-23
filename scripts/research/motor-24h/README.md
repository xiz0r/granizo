# Motor de 24 h: ¿hay algo mejor que v0.2.1?

Se probaron los dos cambios que proponía la revisión del motor, con la misma vara (las mismas falsas alarmas) y validación dejando un año afuera:

- **Disparo junto al ambiente.** Hoy alcanza con que el modelo forme tormentas en cualquier lugar y hora de la ventana. La variante pide que caigan a ±3 h de un punto-hora con ambiente fuerte.
- **Puntaje continuo.** Una logística sobre el percentil 90 de ln(gradiente·WMAXSHEAR), el mejor predictor de la investigación v0.3, por modelo y promediada. Los umbrales de cada nivel se fijan para dar las mismas falsas alarmas que v0.2.1 en entrenamiento.

Resultado (`resultados/calibrar.txt`): **ninguno le gana a v0.2.1**, así que el motor no cambia.

| 109 casos del archivo histórico (39 granizadas, 70 tormentas sin granizo) | "Chances reales" | "Algunas chances" o más |
|---|---|---|
| v0.2.1 | 44% / 10% | 72% / 34% |
| Disparo a ±3 h | 38% / 9% | 72% / 33% |
| Puntaje continuo | 38% / 14% | 77% / 36% |

Detección / falsas alarmas.

- **Con el pronóstico real del día anterior** (22 casos de 2026, 16 con granizo): v0.2.1 detecta 8 de 16 con 2 de 6 falsas alarmas en "Chances reales" y 14 de 16 con 3 de 6 en "Algunas chances". El puntaje continuo ordena mejor esos casos (AUC 0,81 contra 0,67), pero con 6 controles no alcanza para cambiar nada. Vale la pena volver a mirarlo cuando el registro de pronósticos (`data/forecast-log/runs/`) junte una temporada.
- **Combinar los modelos de otra forma** ("cualquiera de los dos", uno solo) mueve el punto entre detección y falsas alarmas, no lo mejora. El grado de alerta "Cualquier señal" ya ofrece la variante que detecta más.

```bash
node scripts/research/motor-24h/descargar.ts historical      # caché de Open-Meteo (reanudable; con el cupo diario corta)
node scripts/research/motor-24h/descargar.ts single-run      # corrida de las 12 UTC del día anterior
node scripts/research/motor-24h/exportar.ts historical .cache/ph_hist.csv
node scripts/research/motor-24h/exportar.ts single-run .cache/ph_runs.csv
python3 scripts/research/motor-24h/calibrar.py .cache/ph_hist.csv .cache/ph_runs.csv
```

`exportar.ts` lee solo la caché. De los 140 casos, 125 tienen archivo de al menos un modelo; los 15 restantes son de 2026 y ya entran en la prueba con pronóstico real.
