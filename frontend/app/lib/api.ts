import type { BracketSnapshot, CurrentSnapshot, LiveSnapshot, ScenariosSnapshot } from "./types";

// In production (GitHub Pages), JSON files sit at <basePath>/data/*.json
// because the cron-job pushes them to /data in the same repo.
// In local dev, we read from a `data/` directory served by `next dev`.
function dataUrl(name: string): string {
  const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
  return `${base}/data/${name}`;
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
