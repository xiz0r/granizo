// Desde cuándo hay datos de cada modelo en cada fuente de Open-Meteo, y qué corrida es "el día anterior".
export const START: Record<'historical' | 'single-run', Record<string, string>> = {
  historical: { gfs_seamless: '2021-03-01', ecmwf_ifs025: '2024-06-01' },
  'single-run': { ecmwf_ifs025: '2024-03-02', gfs_seamless: '2026-04-03' },
};

/** La corrida de las 12 UTC del día anterior (09 h en Uruguay: lo que la app mostraría para "mañana"). */
export function runFor(date: string): string {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 16);
}
