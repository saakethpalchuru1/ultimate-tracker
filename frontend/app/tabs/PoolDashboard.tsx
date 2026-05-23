"use client";
import type { CurrentSnapshot } from "../lib/types";
import { teamMap } from "../lib/api";

export default function PoolDashboard({ current }: { current: CurrentSnapshot }) {
  const tmap = teamMap(current);
  const target = current.target_team_id;

  return (
    <div className="space-y-4">
      {current.standings.map(ps => {
        const games = current.games.filter(g => g.pool === ps.pool);
        const finals = games.filter(g => g.status === "final");
        const remaining = games.filter(g => g.status !== "final");
        return (
          <section key={ps.pool} className="card">
            <header className="mb-2 flex items-baseline justify-between">
              <h2 className="text-base font-semibold">Pool {ps.pool}</h2>
              <span className="text-xs text-zinc-500">
                {finals.length} final · {remaining.length} remaining
              </span>
            </header>

            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-zinc-500">
                <tr><th className="py-1">#</th><th>Team</th><th className="text-right">W-L</th><th className="text-right">PD</th></tr>
              </thead>
              <tbody>
                {ps.ordered_team_ids.map((tid, i) => {
                  const row = ps.rows[tid];
                  const t = tmap[tid];
                  const isTarget = tid === target;
                  return (
                    <tr key={tid} className={isTarget ? "row-target" : ""}>
                      <td className="py-1 pr-2 text-zinc-500">{i + 1}</td>
                      <td>
                        {t?.name ?? tid}
                        <span className="ml-1 text-xs text-zinc-500">({t?.seed})</span>
                      </td>
                      <td className="text-right tabular-nums">{row.wins}-{row.losses}</td>
                      <td className={`text-right tabular-nums ${row.pd > 0 ? "text-favorable" : row.pd < 0 ? "text-bad" : "text-zinc-400"}`}>
                        {row.pd > 0 ? `+${row.pd}` : row.pd}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {ps.tiebreak_trace.length > 0 && (
              <details className="mt-2 text-xs text-zinc-400">
                <summary className="cursor-pointer">Tiebreaker trace ({ps.tiebreak_trace.length} step{ps.tiebreak_trace.length > 1 ? "s" : ""})</summary>
                <ul className="mt-1 space-y-1">
                  {ps.tiebreak_trace.map((tt, idx) => (
                    <li key={idx} className="rounded bg-zinc-800/50 p-2">
                      <span className="pill bg-zinc-700">Rule {tt.rule}</span>{" "}
                      <span className="text-zinc-400">{tt.outcome}</span>{tt.note ? ` — ${tt.note}` : ""}
                      <div className="text-zinc-500">
                        Tied: {tt.tied_team_ids.map(t => tmap[t]?.name ?? t).join(", ")}
                      </div>
                      <div className="text-zinc-500">
                        Metric: {Object.entries(tt.metric_values).map(([k, v]) => `${tmap[k]?.name ?? k}=${v}`).join(", ")}
                      </div>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {remaining.length > 0 && (
              <details className="mt-2 text-xs text-zinc-400" open={ps.pool === tmap[target]?.pool}>
                <summary className="cursor-pointer">Remaining games ({remaining.length})</summary>
                <ul className="mt-1 space-y-0.5">
                  {remaining.map(g => (
                    <li key={g.game_id}>
                      <span className="text-zinc-500">{g.scheduled_at} · F{g.field}</span>{" "}
                      {tmap[g.team1]?.name ?? g.team1} vs {tmap[g.team2]?.name ?? g.team2}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        );
      })}
    </div>
  );
}
