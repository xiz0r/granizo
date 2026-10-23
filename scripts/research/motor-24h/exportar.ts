// Ingredientes por punto-hora de cada caso, leídos SOLO de la caché de Open-Meteo (sin red), en CSV para calibrar.py.
// Uso: node scripts/research/motor-24h/exportar.ts <historical|single-run> <salida.csv>
import '../../../src/data/nodeCache.ts';
import { writeFileSync } from 'node:fs';
import { configureOpenMeteo, fetchProfiles } from '../../../src/data/openMeteo.ts';
import { loadEvents, windowFor } from '../../../src/data/events.ts';
import { neighborhood } from '../../../src/geo/neighborhood.ts';
import { NEIGHBORHOOD } from '../../../src/engine/config.ts';
import { computeIngredients } from '../../../src/engine/ingredients.ts';
import { START, runFor } from './comun.ts';

globalThis.fetch = (async () => {
  throw new Error('sin red: solo caché');
}) as typeof fetch;
configureOpenMeteo({ attempts: 1 });

const [source, out] = process.argv.slice(2) as [keyof typeof START, string];
if (!(source in START) || !out) throw new Error('Uso: exportar.ts <historical|single-run> <salida.csv>');
const rows = ['id,model,time,lat,lon,lapse,wmax,mucape,shear,showers,precip,frz_agl'];
let ok = 0;
let missing = 0;
for (const e of await loadEvents()) {
  const { from, to } = windowFor(e);
  const points = neighborhood({ lat: e.lat, lon: e.lon }, NEIGHBORHOOD.radiusKm, NEIGHBORHOOD.spacingKm);
  for (const [model, start] of Object.entries(START[source])) {
    if ((source === 'historical' ? from : e.date) < start) continue;
    let profiles;
    try {
      profiles = await fetchProfiles(
        source === 'historical'
          ? { source, points, startDate: from.slice(0, 10), endDate: to.slice(0, 10), model }
          : { source, run: runFor(e.date), points, startDate: '', endDate: '', model },
      );
    } catch {
      missing++;
      continue;
    }
    ok++;
    for (const p of profiles) {
      if (p.time < from || p.time > to) continue;
      const i = computeIngredients(p);
      const f = (x: number | null, d = 2) => (x === null ? '' : x.toFixed(d));
      rows.push([e.id, model, p.time, p.lat, p.lon, f(i.lapse700500CKm), f(i.wmaxshearM2s2, 0), f(i.muCapeJkg, 0), f(i.shear06Ms, 1), f(i.showersMm, 1), f(i.precipitationMm, 1), f(i.freezingLevelMAgl, 0)].join(','));
    }
  }
}
writeFileSync(out, rows.join('\n') + '\n');
console.log(`${source}: ${ok} caso-modelos en caché, ${missing} faltan, ${rows.length - 1} punto-horas → ${out}`);
