import type { BracketSnapshot, CurrentSnapshot, LiveSnapshot, ScenariosSnapshot } from "./types";

// Production deploys set NEXT_PUBLIC_DATA_BASE_URL to raw.githubusercontent.com.
// In dev (npm run dev) it's unset so we fall back to relative /data/.
const DATA_BASE = process.env.NEXT_PUBLIC_DATA_BASE_URL || "";
const REPO = process.env.NEXT_PUBLIC_REPO || "saakethpalchuru1/ultimate-tracker";

// raw.gh on the /main/ branch has a 5-min CDN cache. To get sub-2-min freshness
// we ask the GitHub commits API for the latest commit SHA, then fetch data from
// raw.gh URLs pinned to that SHA. Those SHA-pinned URLs are immutable (CDN can
// cache them forever) AND always reflect the exact data at that commit, so we
// see new data the instant a new SHA appears -- no 5-min lag.
//
// The commits API has a 60 req/hr unauthenticated rate limit per IP, so we
// re-check the SHA at most every 60s. If the API call fails or rate-limits, we
// gracefully fall back to /main/ + cache-busting query string (accepts the
// 5-min CDN lag but never breaks).

let cachedSha: string | null = null;
let shaFetchedAt = 0;
const SHA_RECHECK_MS = 60_000;

async function getLatestSha(): Promise<string | null> {
  const now = Date.now();
  if (cachedSha && (now - shaFetchedAt) < SHA_RECHECK_MS) {
    return cachedSha;
  }
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/commits/main`, { cache: "no-store" });
    if (!r.ok) {
      // 403 typically = rate-limited; we'll fall back to /main/ path
      return cachedSha;
    }
    const j = await r.json();
    cachedSha = j.sha;
    shaFetchedAt = now;
    return cachedSha;
  } catch {
    return cachedSha;
  }
}

function dataUrlForName(name: string, sha: string | null): string {
  // Local dev: relative /data/ path
  if (!DATA_BASE) {
    const prefix = process.env.NEXT_PUBLIC_BASE_PATH || "";
    return `${prefix}/data/${name}?t=${Date.now()}`;
  }
  // SHA-pinned path: instant-fresh, immutably cacheable
  if (sha) {
    return `https://raw.githubusercontent.com/${REPO}/${sha}/data/${name}`;
  }
  // Fallback: /main/ path (5-min CDN cache, but always available)
  return `${DATA_BASE}/${name}?t=${Date.now()}`;
}

async function jget<T>(name: string): Promise<T> {
  const sha = DATA_BASE ? await getLatestSha() : null;
  const url = dataUrlForName(name, sha);
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  return (await r.json()) as T;
}

export const fetchCurrent   = () => jget<CurrentSnapshot>("current.json");
export const fetchScenarios = () => jget<ScenariosSnapshot>("scenarios.json");
export const fetchBracket   = () => jget<BracketSnapshot>("bracket.json");
export const fetchLive      = () => jget<LiveSnapshot>("live.json");

export function teamMap(snap: CurrentSnapshot) {
  const m: Record<string, { name: string; seed: number; pool: string }> = {};
  for (const t of snap.teams) m[t.id] = { name: t.name, seed: t.seed, pool: t.pool };
  return m;
}
