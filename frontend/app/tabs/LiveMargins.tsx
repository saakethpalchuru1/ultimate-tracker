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
  const targetName = tmap[target]?.name ?? target;

  if (!live.has_live_games) {
    return (
      <div className="card">
        <h2 className="text-base font-semibold">No live games right now</h2>
        <p className="mt-1 text-sm text-zinc-400">
          This tab fills in once a game flips to "In Progress" on the USAU page.
          Snapshots refresh every 30 seconds during games.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {live.live_games.map(g => {
        const oppName = tmap[g.opponent_id]?.name ?? g.opponent_id;
        const lead = g.current.target_lead_by;
        const leadLabel =
          lead > 0 ? `${targetName} leading by ${lead}` :
          lead < 0 ? `${targetName} trailing by ${-lead}` :
          "Tied";
        return (
          <section key={g.game_id} className="card">
            <header className="mb-3">
              <h2 className="text-base font-semibold">
                {targetName} vs {oppName}
                <span className="ml-2 text-xs text-zinc-500">Field {g.field} · {g.scheduled_at}</span>
              </h2>
              <div className="mt-2 flex items-baseline gap-3">
                <span className="text-2xl font-bold tabular-nums">
                  {g.current.target_score} – {g.current.opponent_score}
                </span>
                <span className={"pill " + (lead > 0 ? "bg-favorable/20 text-favorable" : lead < 0 ? "bg-bad/20 text-bad" : "bg-zinc-700")}>
                  {leadLabel}
                </span>
              </div>
            </header>

            <div className="space-y-2">
              {g.summary.map(s => {
                const finishColor = FINISH_COLOR[s.finish] ?? "text-zinc-300";
                const clinch = s.guaranteed_at_or_above_margin;
                const need = s.margin_delta_needed;
                const ex = s.example_score;
                return (
                  <div key={s.finish} className="rounded border border-zinc-800 p-3">
                    <div className="flex items-baseline justify-between">
                      <span className={"font-semibold text-base " + finishColor}>
                        Finish #{s.finish}
                      </span>
                      {ex && (
                        <span className="text-xs text-zinc-500">
                          e.g. final {ex[0]}–{ex[1]}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm leading-relaxed">
                      {clinch === null && (
                        <span className="text-zinc-400">{s.human_text}</span>
                      )}
                      {clinch !== null && clinch > 0 && (
                        <>
                          <span className="text-zinc-300">Beat {oppName} by </span>
                          <span className="font-bold text-target">{clinch}+ points</span>
                          <span className="text-zinc-300"> to clinch #{s.finish}.</span>
                          {need !== null && need > 0 && (
                            <div className="mt-1 text-xs text-zinc-400">
                              Currently {lead > 0 ? `+${lead}` : lead}; need to outscore {oppName} by
                              <span className="text-target font-semibold"> {need} more</span> the rest of the game.
                            </div>
                          )}
                          {need !== null && need <= 0 && (
                            <div className="mt-1 text-xs text-favorable">Already there — just hold the lead.</div>
                          )}
                        </>
                      )}
                      {clinch !== null && clinch === 0 && (
                        <span className="text-zinc-300">Any win (or even a draw) locks #{s.finish}.</span>
                      )}
                      {clinch !== null && clinch < 0 && (
                        <span className="text-zinc-300">
                          Even losing by up to <span className="font-bold">{-clinch} points</span> still locks #{s.finish}.
                        </span>
                      )}
                    </p>
                  </div>
                );
              })}
            </div>

            <details className="mt-3 text-xs text-zinc-400">
              <summary className="cursor-pointer">Show full margin/combo matrix ({g.matrix.length} rows)</summary>
              <div className="mt-2 max-h-80 overflow-auto">
                <table className="w-full text-xs">
                  <thead className="text-zinc-500">
                    <tr><th className="text-left">Other-games combo</th><th>Final score</th><th>{targetName} finish</th></tr>
                  </thead>
                  <tbody>
                    {g.matrix.map((row, i) => (
                      <tr key={i} className="border-t border-zinc-800/60">
                        <td className="py-0.5 pr-2 text-zinc-500">{row.combo}</td>
                        <td className="text-center font-mono">{row.projected_final_target}–{row.projected_final_opp}</td>
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

      {live.other_live_games && live.other_live_games.length > 0 && (
        <section className="card">
          <h2 className="mb-2 text-base font-semibold">
            Other live games in Pool {live.target_pool}
          </h2>
          <p className="mb-2 text-xs text-zinc-500">
            These games affect {targetName}'s pool finish but don't involve {targetName} directly.
            Watch them — their outcomes shift {targetName}'s margin requirements above.
          </p>
          <ul className="space-y-2">
            {live.other_live_games.map(g => {
              const t1Name = tmap[g.team1]?.name ?? g.team1;
              const t2Name = tmap[g.team2]?.name ?? g.team2;
              const diff = g.score1 - g.score2;
              return (
                <li key={g.game_id} className="rounded border border-zinc-800 p-2">
                  <div className="flex items-baseline justify-between">
                    <span className="text-sm">{t1Name} vs {t2Name}</span>
                    <span className="font-mono tabular-nums">{g.score1} – {g.score2}</span>
                  </div>
                  <div className="text-xs text-zinc-500">
                    {diff > 0 ? `${t1Name} leads by ${diff}` : diff < 0 ? `${t2Name} leads by ${-diff}` : "Tied"}
                    {" · Field "}{g.field} · {g.scheduled_at}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
