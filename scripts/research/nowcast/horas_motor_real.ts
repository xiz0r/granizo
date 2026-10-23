// Como horas_motor.ts, pero con el pronóstico real del día anterior (corrida de las 12 UTC, Single Runs API) que dejó
// en caché scripts/research/motor-24h/descargar.ts single-run. Solo caché, sin red. → .cache/research-nowcast/horas-real.json
import '../../../src/data/nodeCache.ts';
import { writeFileSync } from 'node:fs';
import { assessProfiles } from '../../../src/assess.ts';
import { combineModels } from '../../../src/engine/classify.ts';
import { NEIGHBORHOOD, SENSITIVITY_RULES } from '../../../src/engine/config.ts';
import { configureOpenMeteo, fetchProfiles } from '../../../src/data/openMeteo.ts';
import { loadEvents, windowFor } from '../../../src/data/events.ts';
import { neighborhood } from '../../../src/geo/neighborhood.ts';
import { START, runFor } from '../motor-24h/comun.ts';

globalThis.fetch = (async () => {
  throw new Error('sin red: solo caché');
}) as typeof fetch;
configureOpenMeteo({ attempts: 1 });

const NAMES: Record<string, string> = { gfs_seamless: 'GFS', ecmwf_ifs025: 'ECMWF' };
const dir = new URL('.', import.meta.url).pathname;
const out: Record<string, { level: string; hours: Record<string, string> }> = {};
for (const e of await loadEvents()) {
  const { from, to } = windowFor(e);
  const points = neighborhood({ lat: e.lat, lon: e.lon }, NEIGHBORHOOD.radiusKm, NEIGHBORHOOD.spacingKm);
  const results = [];
  for (const [model, start] of Object.entries(START['single-run'])) {
    if (e.date < start) continue;
    try {
      const profiles = await fetchProfiles({ source: 'single-run', run: runFor(e.date), points, startDate: '', endDate: '', model });
      results.push({ model: NAMES[model], assessment: assessProfiles(profiles, from, to) });
    } catch {
      // sin caché
    }
  }
  if (!results.length) continue;
  const r = combineModels(results, SENSITIVITY_RULES.balanced.combine);
  out[e.id] = { level: r.level, hours: Object.fromEntries(r.hourly.map((h) => [h.time, h.environment])) };
}
writeFileSync(`${dir}../../../.cache/research-nowcast/horas-real.json`, JSON.stringify(out));
console.log(`${Object.keys(out).length} casos con pronóstico real`);
