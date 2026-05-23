"use client";
import type { BracketSnapshot, CurrentSnapshot, ScenariosSnapshot } from "../lib/types";
import { teamMap } from "../lib/api";

export default function TexasPath({
  current, scenarios, bracket,
}: { current: CurrentSnapshot; scenarios: ScenariosSnapshot; bracket: BracketSnapshot }) {
  const tmap = teamMap(current);
  const target = current.target_team_id;
  const summary = scenarios.target_summary;
  const dist = summary?.finish_distribution ?? {};
  const path = bracket.target_path ?? [];

  const total = Object.values(dist).reduce((a, b) => a + b, 0);
  const livePool = current.standings.find(s => s.ordered_team_ids.includes(target));
  const livePlace = livePool ? livePool.ordered_team_ids.indexOf(target) + 1 : null;

  return (
    <div className="space-y-3">
      <section className="card">
        <h2 className="text-base font-semibold">{tmap[target]?.name ?? target} live</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Currently projecting <span className="text-target font-semibold">Pool {tmap[target]?.pool} #{livePlace ?? "?"}</span>{" "}
          based on standings at {new Date(current.generated_at).toLocaleTimeString()}.
        </p>
      </section>

      <section className="card">
        <h3 className="mb-1 text-sm font-semibold">Finish distribution across {total} remaining scenarios</h3>
        <ul className="space-y-1">
          {Object.entries(dist).sort(([a],[b]) => Number(a)-Number(b)).map(([f, n]) => (
            <li key={f} className="flex items-center gap-2 text-sm">
              <span className="w-8 text-zinc-500">#{f}</span>
              <div className="flex-1 h-2 rounded bg-zinc-800">
                <div className="h-2 rounded bg-target" style={{ width: `${(Number(n)/total)*100}%` }} />
              </div>
              <span className="w-12 text-right tabular-nums">{n}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h3 className="mb-1 text-sm font-semibold">Projected bracket path</h3>
        {path.length === 0 ? (
          <p className="text-sm text-zinc-400">
            Not currently projected into the bracket. Win out (or get help) to qualify.
          </p>
        ) : (
          <ul className="space-y-1">
            {path.map(step => (
              <li key={step.game_id} className="text-sm">
                <span className="text-zinc-500">{step.round}</span>{" "}
                vs {step.opponent_team_id
                  ? (tmap[step.opponent_team_id]?.name ?? step.opponent_team_id)
                  : <span className="italic text-zinc-500">{step.opponent_source}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h3 className="mb-1 text-sm font-semibold">Top routes to each finish</h3>
        {[1, 2, 3, 4, 5].map(f => {
          const opts = summary?.scenarios_by_finish[String(f)] ?? [];
          if (opts.length === 0) return null;
          return (
            <details key={f} className="border-t border-zinc-800 py-1 text-sm">
              <summary className="cursor-pointer">
                Finish #{f} — {opts.length} scenario{opts.length > 1 ? "s" : ""}
              </summary>
              <ul className="ml-3 mt-1 list-disc text-xs text-zinc-400">
                {opts.slice(0, 6).map(s => (
                  <li key={s.id}>
                    {s.assumed_outcomes.map(o =>
                      `${tmap[o.winner_id]?.name ?? o.winner_id} beats ${tmap[o.loser_id]?.name ?? o.loser_id}`
                    ).join(" · ")}
                    {s.margin_sensitive && <span className="text-sensitive"> (margin-sensitive)</span>}
                  </li>
                ))}
                {opts.length > 6 && <li className="text-zinc-600">… and {opts.length - 6} more</li>}
              </ul>
            </details>
          );
        })}
      </section>
    </div>
  );
}
