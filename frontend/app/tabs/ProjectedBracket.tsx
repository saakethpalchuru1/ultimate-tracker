"use client";
import type { BracketSnapshot, CurrentSnapshot } from "../lib/types";
import { teamMap } from "../lib/api";

function buildFeedsInto(bracket: BracketSnapshot): Record<string, string> {
  // For each game G, find the next-round game that lists "Winner of G" as a participant.
  // Returns { "PQ1": "QF1", "QF1": "SF1", "SF1": "F", ... }
  const map: Record<string, string> = {};
  for (const rnd of bracket.rounds) {
    for (const g of rnd.games) {
      for (const p of g.participants) {
        const m = p.source.match(/Winner of (\S+)/);
        if (m) map[m[1]] = g.id;
      }
    }
  }
  return map;
}

export default function ProjectedBracket({
  bracket, current,
}: { bracket: BracketSnapshot; current: CurrentSnapshot }) {
  const tmap = teamMap(current);
  const target = current.target_team_id;
  const feedsInto = buildFeedsInto(bracket);

  return (
    <div>
      <p className="mb-3 text-xs text-zinc-500">
        Pool finishes feed left → right. Pool winners go directly to quarters;
        pool 2nd / 3rd play prequarters (A↔D and B↔C crossovers). Downstream
        rounds show <span className="italic">Winner of X</span> until the
        feeding game finalizes.
      </p>
      <div className="flex gap-3 overflow-x-auto pb-3" style={{ minHeight: "620px" }}>
        {bracket.rounds.map((rnd, roundIdx) => (
          <div key={rnd.name}
               className="flex w-56 flex-shrink-0 flex-col"
               style={{ marginTop: `${roundIdx * 14}px` }}>
            <h2 className="mb-2 text-center text-xs font-semibold uppercase tracking-wide text-zinc-400">
              {rnd.name}
            </h2>
            <div className="flex flex-1 flex-col"
                 style={{ justifyContent: "space-around", gap: "12px" }}>
              {rnd.games.map(g => {
                const feeds = feedsInto[g.id];
                return (
                  <div key={g.id}
                       className="rounded-md border border-zinc-800 bg-zinc-900 p-2">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-[10px] uppercase tracking-wide text-zinc-500">
                        {g.id}
                      </span>
                      {feeds ? (
                        <span className="text-[10px] text-zinc-500">→ {feeds}</span>
                      ) : (
                        <span className="text-[10px] text-favorable">🏆 Champion</span>
                      )}
                    </div>
                    {g.participants.map((p, idx) => {
                      const isWinnerSource = p.source.startsWith("Winner of");
                      if (isWinnerSource) {
                        // Placeholder ONLY — never auto-fill from projection.
                        return (
                          <div key={idx} className="text-sm italic text-zinc-500 truncate">
                            {p.source}
                          </div>
                        );
                      }
                      // Pool-source participant: show the resolved team if available
                      const isTarget = p.team_id === target;
                      const name = p.team_id ? (tmap[p.team_id]?.name ?? p.team_id) : null;
                      return (
                        <div key={idx}
                             className={"flex items-baseline justify-between text-sm " +
                                        (isTarget ? "text-target font-semibold" : "text-zinc-200")}>
                          <span className="truncate">
                            {name ?? <span className="italic text-zinc-500">{p.source}</span>}
                          </span>
                          <span className="ml-2 shrink-0 text-[10px] text-zinc-500">
                            {p.source}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
