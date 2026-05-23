import type { BracketSnapshot, CurrentSnapshot, LiveSnapshot, ScenariosSnapshot } from "./types";

// Where to fetch live JSON from. In production we use a raw.githubusercontent
// URL so every cron push is immediately visible without rebuilding the static
// site. In local dev (next dev) we fall back to a relative /data/ path.
function dataUrl(name: string): string {
  const base = process.env.NEXT_PUBLIC_DATA_BASE_URL;
  if (base) return `${base}/${name}?t=${Date.now()}`;
  const prefix = process.env.NEXT_PUBLIC_BASE_PATH || "";
  return `${prefix}/data/${name}?t=${Date.now()}`;
}

async function jget<T>(name: string): Promise<T> {
  const r = await fetch(dataUrl(name), { cache: "no-store" });
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  return (await r.json()) as T;
}

export const fetchCurrent = () => jget<CurrentSnapshot>("current.json");
export const fetchScenarios = () => jget<ScenariosSnapshot>("scenarios.json");
export const fetchBracket = () => jget<BracketSnapshot>("bracket.json");
export const fetchLive = () => jget<LiveSnapshot>("live.json");

export function teamMap(snap: CurrentSnapshot) {
  const m: Record<string, { name: string; seed: number; pool: string }> = {};
  for (const t of snap.teams) m[t.id] = { name: t.name, seed: t.seed, pool: t.pool };
  return m;
}
