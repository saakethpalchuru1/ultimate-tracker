"use client";
import { useEffect, useState } from "react";
import { fetchBracket, fetchCurrent, fetchLive, fetchScenarios, teamMap } from "./lib/api";
import type { BracketSnapshot, CurrentSnapshot, LiveSnapshot, ScenariosSnapshot } from "./lib/types";
import PoolDashboard from "./tabs/PoolDashboard";
import ScenarioMatrix from "./tabs/ScenarioMatrix";
import ProjectedBracket from "./tabs/ProjectedBracket";
import TexasPath from "./tabs/TexasPath";
import LiveMargins from "./tabs/LiveMargins";

type Tab = "pools" | "live" | "scenarios" | "bracket" | "texas";
const TABS: { id: Tab; label: string }[] = [
  { id: "pools",     label: "Pools" },
  { id: "live",      label: "Live" },
  { id: "scenarios", label: "Scenarios" },
  { id: "bracket",   label: "Bracket" },
  { id: "texas",     label: "Texas" },
];

export default function Page() {
  const [tab, setTab] = useState<Tab>("pools");
  const [current, setCurrent] = useState<CurrentSnapshot | null>(null);
  const [scenarios, setScenarios] = useState<ScenariosSnapshot | null>(null);
  const [bracket, setBracket] = useState<BracketSnapshot | null>(null);
  const [live, setLive] = useState<LiveSnapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  async function reload() {
    try {
      const [c, s, b, l] = await Promise.all([
        fetchCurrent(), fetchScenarios(), fetchBracket(), fetchLive()
      ]);
      setCurrent(c); setScenarios(s); setBracket(b); setLive(l); setErr(null);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setLastChecked(new Date());
    }
  }
  useEffect(() => {
    reload();
    // Re-fetch every 60s. The data underneath is regenerated every 5 min by
    // the cron, but checking minutely catches new pushes quickly.
    const t = setInterval(reload, 60_000);
    return () => clearInterval(t);
  }, []);

  const tmap = current ? teamMap(current) : {};
  const liveBadge = live?.has_live_games ? " 🔴" : "";

  return (
    <div>
      <header className="mb-3">
        <div className="flex items-baseline justify-between">
          <h1 className="text-lg font-semibold">2026 D-I Men's — Live Tracker</h1>
          <button onClick={reload} className="text-xs text-zinc-400 underline">refresh</button>
        </div>
        {current && (
          <p className="text-xs text-zinc-500">
            Snapshot {new Date(current.generated_at).toLocaleTimeString()}
            {lastChecked && <> · checked {lastChecked.toLocaleTimeString()}</>} ·
            Target: <span className="text-target">{tmap[current.target_team_id]?.name ?? current.target_team_id}</span>
          </p>
        )}
        {err && <p className="mt-2 text-xs text-bad">Error loading: {err}</p>}
      </header>

      <nav className="sticky top-0 z-10 mb-3 flex border-b border-zinc-800 bg-[#0b0d10]/95 backdrop-blur">
        {TABS.map(t => (
          <button key={t.id}
            className={"tab-btn " + (tab === t.id ? "tab-btn-active" : "")}
            onClick={() => setTab(t.id)}>
            {t.label}{t.id === "live" && liveBadge}
          </button>
        ))}
      </nav>

      {tab === "pools"     && current   && <PoolDashboard current={current} />}
      {tab === "live"      && live && current && <LiveMargins live={live} current={current} />}
      {tab === "scenarios" && scenarios && current && <ScenarioMatrix scenarios={scenarios} current={current} />}
      {tab === "bracket"   && bracket   && current && <ProjectedBracket bracket={bracket} current={current} />}
      {tab === "texas"     && current && scenarios && bracket &&
        <TexasPath current={current} scenarios={scenarios} bracket={bracket} />}
      {!current && !err && <p className="text-sm text-zinc-500">Loading…</p>}
    </div>
  );
}
