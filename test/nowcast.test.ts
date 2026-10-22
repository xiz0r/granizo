import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NOWCAST } from '../src/engine/config.ts';
import { assessPointHour, assessWindow } from '../src/engine/classify.ts';
import type { Ingredients } from '../src/engine/types.ts';
import { nowcastAlert, nowcastAt } from '../src/nowcast.ts';
import { present } from '../src/presenter.ts';

// Montevideo; 0,1° de latitud ≈ 11 km.
const LAT = -34.9;
const LON = -56.16;
const NOW = Date.parse('2026-10-22T19:40:00Z');

/** JSON como el de scripts/nowcast/build.py: celdas [lat, lon, rayos últimos 10 min, 10–20, 20–30]. */
const doc = (cells: number[][], toUtc = '2026-10-22T19:27:36Z') => ({
  version: 1,
  generatedUtc: '2026-10-22T19:28:36Z',
  lightning: { toUtc, grid: { cellDeg: 0.1, slotMin: 10, cells } },
  rain: { validUtc: '2026-10-22T19:10:00Z', grid: { cellDeg: 0.1, minMmH: 1, cells: [[LAT, LON, 12.5], [LAT + 1, LON, 40]] } },
  radar: [
    { id: 'sg', name: 'Santiago/RS', status: 'ok', frames: [{ utc: '2026-10-22T19:16:24Z', png: 'https://x/sg.png', bounds: [-32.8, -25.6, -59.2, -50.8] }] },
    { id: 'cn', name: 'Canguçu/RS', status: 'sin datos', frames: [] },
  ],
});

test('cuenta los rayos a ≤ 20 km en la media hora y da la distancia a la celda más cercana', () => {
  const n = nowcastAt(doc([[LAT + 0.1, LON, 2, 1, 0], [LAT - 0.1, LON + 0.1, 0, 0, 4], [LAT + 0.3, LON, 9, 9, 9]]), LAT, LON, NOW);
  assert.ok(n);
  assert.equal(n.flashes, 7); // las dos celdas a ~11 y ~15 km; la de ~33 km no suma
  assert.equal(n.flashesLast10, 2);
  assert.equal(n.nearestKm, 11);
  assert.equal(n.ageMin, 12);
  assert.equal(n.rainMaxMmH, 12.5);
  assert.deepEqual(n.radar.map((r) => r.id), ['sg']);
});

test('sin rayos cerca: nada que informar; datos viejos o rotos: null', () => {
  assert.equal(nowcastAt(doc([[LAT + 1, LON, 5, 5, 5]]), LAT, LON, NOW)?.nearestKm, null);
  assert.equal(nowcastAt(doc([[LAT, LON, 5, 0, 0]], '2026-10-22T18:30:00Z'), LAT, LON, NOW), null); // > maxAgeMin
  assert.equal(nowcastAt({ lightning: { error: 'sin archivos GLM' } }, LAT, LON, NOW), null);
  assert.equal(nowcastAt(null, LAT, LON, NOW), null);
});

test(`aviso: motor ≥ "Algunas chances" y ≥ ${NOWCAST.minFlashes} rayos a ≤ ${NOWCAST.radiusKm} km`, () => {
  const near = nowcastAt(doc([[LAT + 0.1, LON, 1, 1, 1]]), LAT, LON, NOW);
  const few = nowcastAt(doc([[LAT + 0.1, LON, 1, 1, 0]]), LAT, LON, NOW);
  assert.equal(nowcastAlert(near, 'watch'), true);
  assert.equal(nowcastAlert(near, 'protect'), true);
  assert.equal(nowcastAlert(near, 'calm'), false);
  assert.equal(nowcastAlert(few, 'protect'), false);
  assert.equal(nowcastAlert(null, 'protect'), false);
});

const base: Ingredients = {
  muCapeJkg: 2000, muCinJkg: -20, muMixingRatioGkg: 13, muStartHpa: 900, shear06Ms: 30, lapse700500CKm: 7.2, t500C: -13,
  freezingLevelMAgl: 3800, ship: 1.2, wmaxshearM2s2: 1897, showersMm: 2, precipitationMm: 4, modelCapeJkg: 1800,
};
const win = { name: 'next24h', label: 'Próximas 24 h', from: '2026-08-27T20:00', to: '2026-08-28T19:00' };

test('el presentador pone el aviso "Ahora" solo con ambiente de granizo; si no, informa la tormenta', () => {
  const hail = assessWindow([assessPointHour('2026-08-27T23:00', LAT, LON, base)]);
  const calm = assessWindow([assessPointHour('2026-08-27T23:00', LAT, LON, { ...base, lapse700500CKm: 5 })]);
  const n = nowcastAt(doc([[LAT + 0.1, LON, 3, 0, 0]]), LAT, LON, NOW);
  const alert = present(hail, win, '2026-08-27T20:00', 'balanced', undefined, 'es', n).now;
  assert.equal(alert?.alert, true);
  assert.match(alert!.text, /Rayos a 11 km hace 12 min.*cubrilo ahora/);
  const info = present(calm, win, '2026-08-27T20:00', 'balanced', undefined, 'en', n).now;
  assert.deepEqual(info, { alert: false, strong: 'Thunderstorm.', text: 'Lightning 11 km away 12 min ago.' });
  assert.equal(present(hail, win, '2026-08-27T20:00').now, null);
});
