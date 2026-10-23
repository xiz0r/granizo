// Lo que la app de hoy muestra para cada caso: el nivel de la ventana y la tira de horas (ambiente hora por hora, sin
// pasar del nivel), con el motor actual y GFS + ECMWF combinados como en la app. Lee SOLO la caché de Open-Meteo (la de
// npm run backtest y de niveles_metar.ts), sin red. Casos de data/events.json y de casos_metar.json.
// Uso: node scripts/research/nowcast/horas_motor.ts → .cache/research-nowcast/horas.json
import '../../../src/data/nodeCache.ts';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { assessProfiles } from '../../../src/assess.ts';
import { combineModels } from '../../../src/engine/classify.ts';
import { NEIGHBORHOOD, SENSITIVITY_RULES } from '../../../src/engine/config.ts';
import { configureOpenMeteo, fetchProfiles } from '../../../src/data/openMeteo.ts';
import { loadEvents, windowFor, type HailEvent } from '../../../src/data/events.ts';
import { neighborhood } from '../../../src/geo/neighborhood.ts';

globalThis.fetch = (async () => {
  throw new Error('sin red: solo caché');
}) as typeof fetch;
configureOpenMeteo({ attempts: 1 });

const START: Record<string, string> = { gfs_seamless: '2021-03-01', ecmwf_ifs025: '2024-06-01' };
const NAMES: Record<string, string> = { gfs_seamless: 'GFS', ecmwf_ifs025: 'ECMWF' };
const dir = new URL('.', import.meta.url).pathname;
const metar: HailEvent[] = JSON.parse(readFileSync(`${dir}casos_metar.json`, 'utf8'));
const out: Record<string, { level: string; from: string; to: string; hours: Record<string, string> }> = {};
for (const e of [...(await loadEvents()), ...metar]) {
  const { from, to } = windowFor(e);
  const points = neighborhood({ lat: e.lat, lon: e.lon }, NEIGHBORHOOD.radiusKm, NEIGHBORHOOD.spacingKm);
  const results = [];
  for (const [model, start] of Object.entries(START)) {
    if (from < start) continue;
    try {
      const profiles = await fetchProfiles({ source: 'historical', points, startDate: from.slice(0, 10), endDate: to.slice(0, 10), model });
      results.push({ model: NAMES[model], assessment: assessProfiles(profiles, from, to) });
    } catch {
      // sin caché para ese modelo
    }
  }
  if (!results.length) continue;
  const r = combineModels(results, SENSITIVITY_RULES.balanced.combine);
  out[e.id] = { level: r.level, from, to, hours: Object.fromEntries(r.hourly.map((h) => [h.time, h.environment])) };
}
mkdirSync(`${dir}../../../.cache/research-nowcast`, { recursive: true });
writeFileSync(`${dir}../../../.cache/research-nowcast/horas.json`, JSON.stringify(out));
console.log(`${Object.keys(out).length} casos con tira de horas`);
