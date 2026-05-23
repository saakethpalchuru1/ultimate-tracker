"use client";
import type { CurrentSnapshot, LiveSnapshot } from "../lib/types";
import { teamMap } from "../lib/api";

const FINISH_COLOR: Record<number, string> = {
  1: "text-favorable",
  2: "text-favorable",
  3: "text-sensitive",
  4: "text-bad",
  5: "text-bad",
};

export default function LiveMargins({
  live, current,
}: { live: LiveSnapshot; current: CurrentSnapshot }) {
  const tmap = teamMap(current);
  const target = current.target_team_id;

  if (!live.has_live_games) {
    return (
      <div className="card">
        <h2 className="text-base font-semibold">No live games for {tmap[target]?.name ?? target}</h2>
        <p className="mt-1 text-sm text-zinc-400">
          This tab fills in automatically once a {tmap[target]?.name ?? target} game flips to "In Progress" on the USAU page.
          The scraper updates every 5 minutes; running scores power the margin calculations.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {live.live_games.map(g => {
        const opp = tmap[g.opponent_id]?.name ?? g.opponent_id;
        const lead = g.current.target_lead_by;
        return (
          <section key={g.game_id} className="card">
            <header className="mb-2 flex items-baseline justify-between">
              <h2 className="text-base font-semibold">
                {tmap[target]?.name ?? target} vs {opp}
              </h2>
              <span className={"pill " + (lead > 0 ? "bg-favorable/20 text-favorable" : lead < 0 ? "bg-bad/20 text-bad" : "bg-zinc-700")}>
                {g.current.target_score}-{g.current.opponent_score} ({lead > 0 ? `+${lead}` : lead})
              </span>
            </header>

            <p className="text-xs text-zinc-500">
              Field {g.field} · {g.scheduled_at}
            </p>

            <div className="mt-3 space-y-2">
              {g.summary.map(s => (
                <div key={s.finish} className="rounded border border-zinc-800 p-2">
                  <div className="flex items-baseline justify-between">
                    <span className={"font-semibold " + (FINISH_COLOR[s.finish] ?? "text-zinc-300")}>
                      Finish #{s.finish}
                    </span>
                    <span className="text-xs text-zinc-500">
                      min margin: {fmt(s.achievable_min_margin)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm">
                    {s.guaranteed_at_or_above_margin === null ? (
                      <span className="text-zinc-400">
                        Not guaranteed at any final margin (depends on other unfinished games).
                      </span>
                    ) : (
                      <>
                        Guaranteed at final margin{" "}
                        <span className="font-mono text-target">≥ {fmt(s.guaranteed_at_or_above_margin)}</span>
                        {s.margin_delta_needed !== null && s.margin_delta_needed > 0 && (
                          <> · need to extend lead by <span className="font-mono">+{s.margin_delta_needed}</span> from here</>
                        )}
                        {s.margin_delta_needed !== null && s.margin_delta_needed <= 0 && (
                          <> · <span className="text-favorable">already there</span></>
                        )}
                      </>
                    )}
                  </p>
                </div>
              ))}
            </div>

            <details className="mt-3 text-xs text-zinc-400">
              <summary className="cursor-pointer">Show full margin matrix ({g.matrix.length} rows)</summary>
              <div className="mt-2 max-h-80 overflow-auto">
                <table className="w-full text-xs">
                  <thead className="text-zinc-500">
                    <tr><th className="text-left">Other games</th><th>Final margin</th><th>Finish</th></tr>
                  </thead>
                  <tbody>
                    {g.matrix.map((row, i) => (
                      <tr key={i} className="border-t border-zinc-800/60">
                        <td className="py-0.5 pr-2 text-zinc-500">{row.combo}</td>
                        <td className="text-center font-mono">{row.target_final_margin >= 0 ? `+${row.target_final_margin}` : row.target_final_margin}</td>
                        <td className={"text-center font-semibold " + (FINISH_COLOR[row.target_finish] ?? "")}>#{row.target_finish}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
        );
      })}
    </div>
  );
}

function fmt(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return n > 0 ? `+${n}` : String(n);
}
