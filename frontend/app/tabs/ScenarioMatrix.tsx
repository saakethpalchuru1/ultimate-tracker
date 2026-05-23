"use client";
import { useMemo } from "react";
import type { CurrentSnapshot, ScenariosSnapshot } from "../lib/types";
import { teamMap } from "../lib/api";

const FINISH_BG: Record<number, string> = {
  1: "bg-favorable/20 text-favorable",
  2: "bg-favorable/10 text-favorable",
  3: "bg-sensitive/20 text-sensitive",
  4: "bg-bad/15 text-bad",
  5: "bg-bad/25 text-bad",
};

export default function ScenarioMatrix({
  scenarios, current,
}: { scenarios: ScenariosSnapshot; current: CurrentSnapshot }) {
  const tmap = teamMap(current);
  const target = current.target_team_id;
  const targetPool = tmap[target]?.pool ?? "A";
  const data = scenarios.pools[targetPool];

  const rows = useMemo(() => {
    if (!data) return [];
    return data.permutations.map(p => ({
      id: p.id,
      assumed: p.assumed_outcomes,
      finish: p.target_finish ?? 0,
      margin_sensitive: p.margin_sensitive,
    })).sort((a, b) => a.finish - b.finish || a.id - b.id);
  }, [data]);

  if (!data) return <p className="text-sm text-zinc-400">No scenarios for this pool yet.</p>;

  const dist = scenarios.target_summary?.finish_distribution ?? {};

  return (
    <div className="space-y-4">
      <section className="card">
        <h2 className="mb-2 text-base font-semibold">
          Pool {targetPool} · {data.n_remaining} remaining · {data.n_permutations} permutations
        </h2>
        <div className="flex flex-wrap gap-1">
          {Object.entries(dist).sort(([a],[b]) => Number(a)-Number(b)).map(([finish, n]) => (
            <span key={finish} className={"pill " + (FINISH_BG[Number(finish)] ?? "bg-zinc-700")}>
              {tmap[target]?.name ?? target} #{finish}: {n}
            </span>
          ))}
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          Green = favorable finish · Yellow = margin-sensitive · Red = bad finish.
          Margin-sensitive rows depend on the exact margin of a game and may flip with a different score.
        </p>
      </section>

      <section className="card overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead className="text-left text-zinc-500">
            <tr>
              <th className="py-1 pr-2">#</th>
              {data.permutations[0]?.assumed_outcomes.map(o => (
                <th key={o.game_id} className="px-1 whitespace-nowrap">
                  {labelGame(o.game_id, current)}
                </th>
              ))}
              <th className="pl-2 text-right">{tmap[target]?.name ?? target}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} className={"border-t border-zinc-800 " + (r.margin_sensitive ? "bg-sensitive/5" : "")}>
                <td className="py-1 pr-2 text-zinc-600">{r.id}</td>
                {r.assumed.map(o => (
                  <td key={o.game_id} className="px-1 whitespace-nowrap">
                    {tmap[o.winner_id]?.name ?? o.winner_id}
                  </td>
                ))}
                <td className={"pl-2 text-right font-medium " + (FINISH_BG[r.finish] ?? "")}>
                  #{r.finish}{r.margin_sensitive ? "*" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function labelGame(gameId: string, current: CurrentSnapshot) {
  const g = current.games.find(x => x.game_id === gameId);
  if (!g) return gameId;
  return `${initials(g.team1, current)} vs ${initials(g.team2, current)}`;
}
function initials(tid: string, current: CurrentSnapshot) {
  const name = current.teams.find(t => t.id === tid)?.name ?? tid;
  return name.split(/[\s-]+/).map(w => w[0]).join("").slice(0, 3).toUpperCase();
}
