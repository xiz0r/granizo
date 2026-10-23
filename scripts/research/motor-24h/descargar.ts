// Llena la caché de Open-Meteo (.cache/open-meteo) con lo que necesita exportar.ts, caso por caso. Reanudable: lo que ya
// está en caché no se vuelve a pedir. Con el límite por hora espera; con el diario corta (volver a correrlo al otro día).
//   historical: el archivo histórico, con los mismos pedidos que el backtest (GFS desde 2021-03, ECMWF desde 2024-06).
//   single-run: el pronóstico real del día anterior (corrida de las 12 UTC), ECMWF desde 2024-03 y GFS desde 2026-04.
// Uso: node scripts/research/motor-24h/descargar.ts <historical|single-run>
import '../../../src/data/nodeCache.ts';
import { fetchProfiles, RateLimitError } from '../../../src/data/openMeteo.ts';
import { loadEvents, windowFor } from '../../../src/data/events.ts';
import { neighborhood } from '../../../src/geo/neighborhood.ts';
import { NEIGHBORHOOD } from '../../../src/engine/config.ts';
import { START, runFor } from './comun.ts';

const source = process.argv[2] as keyof typeof START;
if (!(source in START)) throw new Error('Uso: descargar.ts <historical|single-run>');
// Primero los casos con hora (los que usa también el aviso "Ahora").
const events = (await loadEvents()).sort((a, b) => Number(!a.localTime) - Number(!b.localTime));
let done = 0;
for (const e of events) {
  const { from, to } = windowFor(e);
  const points = neighborhood({ lat: e.lat, lon: e.lon }, NEIGHBORHOOD.radiusKm, NEIGHBORHOOD.spacingKm);
  for (const [model, start] of Object.entries(START[source])) {
    if ((source === 'historical' ? from : e.date) < start) continue;
    for (;;) {
      try {
        await fetchProfiles(
          source === 'historical'
            ? { source, points, startDate: from.slice(0, 10), endDate: to.slice(0, 10), model }
            : { source, run: runFor(e.date), points, startDate: '', endDate: '', model },
        );
        break;
      } catch (err) {
        if (!(err instanceof RateLimitError)) {
          console.log(`✗ ${e.id} ${model}: ${String(err).slice(0, 160)}`);
          break;
        }
        if (/daily/i.test(err.message)) {
          console.log(`Límite diario en ${e.id} ${model}, después de ${done} casos`);
          process.exit(2);
        }
        const wait = (61 - new Date().getUTCMinutes()) * 60_000;
        console.log(`Límite por hora en ${e.id} ${model}: espero ${Math.round(wait / 60000)} min`);
        await new Promise((r) => setTimeout(r, wait));
      }
    }
  }
  if (++done % 10 === 0) console.log(`${done}/${events.length} casos`);
}
console.log(`Listo: ${done} casos`);
