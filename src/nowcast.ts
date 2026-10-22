// "Ahora": lo que está pasando cerca, desde el JSON que publica .github/workflows/nowcast.yml cada 10 minutos
// (scripts/nowcast/build.py). Sin I/O: recibe el JSON ya descargado y la ubicación.
import { NOWCAST } from './engine/config.ts';
import type { RiskLevel } from './engine/types.ts';

export interface RadarFrame {
  id: string;
  name: string;
  utc: string;
  png: string;
  /** [latMin, latMax, lonMin, lonMax] de la imagen. */
  bounds: [number, number, number, number];
}

export interface Nowcast {
  /** Minutos entre el último rayo que cubren los datos y `now`. */
  ageMin: number;
  /** Rayos a ≤ NOWCAST.radiusKm en la media hora que cubren los datos. */
  flashes: number;
  /** Lo mismo, solo en los últimos 10 minutos de los datos. */
  flashesLast10: number;
  /** Distancia a la celda con rayos más cercana (km), hasta NOWCAST.lookKm; null si no hay. */
  nearestKm: number | null;
  /** Lluvia estimada por satélite, máximo a ≤ NOWCAST.radiusKm (mm/h); null sin dato. */
  rainMaxMmH: number | null;
  /** Última imagen de cada radar que la tiene (REDEMET). */
  radar: RadarFrame[];
}

type Cells = number[][];
interface Doc {
  lightning?: { toUtc?: string; grid?: { cells?: Cells } };
  rain?: { grid?: { cells?: Cells } };
  radar?: { id: string; name: string; status: string; frames?: { utc: string; png: string; bounds: number[] }[] }[];
}

const km = (lat0: number, lon0: number, lat: number, lon: number) =>
  Math.hypot((lat - lat0) * 111.32, (lon - lon0) * 111.32 * Math.cos((lat0 * Math.PI) / 180));

/** Lo que dice el JSON para un lugar, o null si falta o está viejo (más de NOWCAST.maxAgeMin). */
export function nowcastAt(doc: unknown, lat: number, lon: number, nowMs: number): Nowcast | null {
  const d = doc as Doc | null;
  const to = d?.lightning?.toUtc ? Date.parse(d.lightning.toUtc) : NaN;
  const cells = d?.lightning?.grid?.cells;
  if (!Number.isFinite(to) || !Array.isArray(cells)) return null;
  const ageMin = (nowMs - to) / 60_000;
  if (ageMin > NOWCAST.maxAgeMin) return null;

  let flashes = 0;
  let flashesLast10 = 0;
  let nearestKm: number | null = null;
  for (const [clat, clon, ...slots] of cells) {
    const dist = km(lat, lon, clat, clon);
    if (dist <= NOWCAST.lookKm && (nearestKm === null || dist < nearestKm)) nearestKm = dist;
    if (dist > NOWCAST.radiusKm) continue;
    flashes += slots.reduce((s, n) => s + n, 0);
    flashesLast10 += slots[0] ?? 0;
  }

  let rainMaxMmH: number | null = d?.rain?.grid?.cells ? 0 : null;
  for (const [clat, clon, mmh] of d?.rain?.grid?.cells ?? []) {
    if (km(lat, lon, clat, clon) <= NOWCAST.radiusKm) rainMaxMmH = Math.max(rainMaxMmH ?? 0, mmh);
  }

  const radar: RadarFrame[] = (d?.radar ?? []).flatMap((r) => {
    const f = r.status === 'ok' ? r.frames?.at(-1) : undefined;
    return f ? [{ id: r.id, name: r.name, utc: f.utc, png: f.png, bounds: f.bounds as RadarFrame['bounds'] }] : [];
  });

  return { ageMin: Math.max(0, Math.round(ageMin)), flashes, flashesLast10, nearestKm: nearestKm === null ? null : Math.round(nearestKm), rainMaxMmH, radar };
}

/**
 * Aviso "Ahora": el motor ve ambiente de granizo para hoy (NOWCAST.minLevel o más) Y hay una tormenta eléctrica
 * activa cerca (NOWCAST.minFlashes rayos o más a ≤ NOWCAST.radiusKm en la última media hora de datos).
 */
export function nowcastAlert(n: Nowcast | null, level: RiskLevel): boolean {
  if (!n) return false;
  const rank: Record<RiskLevel, number> = { calm: 0, watch: 1, protect: 2 };
  return rank[level] >= rank[NOWCAST.minLevel] && n.flashes >= NOWCAST.minFlashes;
}
