"use client";
import type { BracketSnapshot, CurrentSnapshot } from "../lib/types";
import { teamMap } from "../lib/api";

export default function ProjectedBracket({
  bracket, current,
}: { bracket: BracketSnapshot; current: CurrentSnapshot }) {
  const tmap = teamMap(current);
  const target = current.target_team_id;

  return (
    <div className="space-y-3">
      {bracket.rounds.map(rnd => (
        <section key={rnd.name} className="card">
          <h2 className="mb-2 text-base font-semibold">{rnd.name}</h2>
          <ul className="space-y-2">
            {rnd.games.map(g => (
              <li key={g.id} className="rounded border border-zinc-800 p-2">
                <div className="mb-1 text-xs text-zinc-500">{g.id}</div>
                {g.participants.map(p => (
                  <div key={p.side} className={"flex justify-between text-sm " + (p.team_id === target ? "text-target font-semibold" : "")}>
                    <span>
                      {p.team_id ? (tmap[p.team_id]?.name ?? p.team_id) : <span className="italic text-zinc-500">{p.source}</span>}
                    </span>
                    <span className="text-xs text-zinc-500">{p.source}</span>
                  </div>
                ))}
                <div className="mt-1 text-xs text-zinc-500">
                  Projected: {g.projected_winner ? (tmap[g.projected_winner]?.name ?? g.projected_winner) : "TBD"}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
