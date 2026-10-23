// Nivel del motor (equilibrado, GFS + ECMWF) para los casos de casos_metar.json, con el archivo histórico de Open-Meteo
// y la misma ventana que el backtest (18 h antes a 5 h después de la hora del caso). Guarda niveles_metar.json.
// Reanudable: lo bajado queda en la caché de .cache/open-meteo. Antes de 2021-03 no hay archivo: esos casos no tienen nivel.
// Uso: node scripts/research/nowcast/niveles_metar.ts
import '../../../src/data/nodeCache.ts';
import { readFileSync, writeFileSync } from 'node:fs';
import { assess } from '../../../src/assess.ts';
import { RateLimitError } from '../../../src/data/openMeteo.ts';
import { windowFor, type HailEvent } from '../../../src/data/events.ts';

const dir = new URL('.', import.meta.url).pathname;
const cases: HailEvent[] = JSON.parse(readFileSync(`${dir}casos_metar.json`, 'utf8'));
const outPath = `${dir}niveles_metar.json`;
let out: Record<string, string> = {};
try {
  out = JSON.parse(readFileSync(outPath, 'utf8'));
} catch {
  // primera corrida
}
for (const e of cases) {
  if (out[e.id] || e.date < '2021-03-02') continue;
  const { from, to } = windowFor(e);
  try {
    const r = await assess({ center: { lat: e.lat, lon: e.lon }, from, to, source: 'historical' });
    out[e.id] = r.level;
    console.log(`${e.id} → ${r.level}`);
  } catch (err) {
    if (err instanceof RateLimitError) {
      console.log(`Límite de Open-Meteo en ${e.id}: ${err.message}`);
      break;
    }
    console.log(`✗ ${e.id}: ${String(err).slice(0, 160)}`);
  }
  writeFileSync(outPath, JSON.stringify(out, null, 1) + '\n');
}
console.log(`${Object.keys(out).length}/${cases.length} casos con nivel`);
