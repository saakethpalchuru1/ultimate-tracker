"""
Compute pool standings from a list of games.

The pipeline is:
  1. Aggregate W/L/PF/PA per team (final games only).
     If `include_in_progress=True`, an in-progress game with a running
     score is also counted -- treated as "final if the game ended right
     now". This is what powers the LIVE dashboard.
  2. Group teams by W-L record.
  3. For each multi-team group, call the tiebreaker engine.
  4. Concatenate groups (best record -> worst) to produce final order.
"""
from __future__ import annotations

from ..models import Game, PoolStanding, StandingRow
from .tiebreaker import order_teams, TieBreakTrace


def compute_pool_standing(
    pool: str,
    team_ids: list[str],
    games: list[Game],
    *,
    include_in_progress: bool = False,
) -> PoolStanding:
    rows: dict[str, StandingRow] = {tid: StandingRow(team_id=tid) for tid in team_ids}

    # Virtualize in-progress games as "final at current score" without
    # mutating the input Game objects.
    effective_games: list[Game] = []
    for g in games:
        if g.pool != pool:
            continue
        if g.is_final:
            effective_games.append(g)
        elif include_in_progress and g.status == "in_progress" and g.score1 is not None:
            effective_games.append(Game(
                game_id=g.game_id, pool=g.pool,
                team1=g.team1, team2=g.team2,
                score1=g.score1, score2=g.score2,
                status="final",
                scheduled_at=g.scheduled_at, field=g.field,
            ))

    for g in effective_games:
        if g.team1 not in rows or g.team2 not in rows:
            continue
        rows[g.team1].pf += g.score1
        rows[g.team1].pa += g.score2
        rows[g.team2].pf += g.score2
        rows[g.team2].pa += g.score1
        w = g.winner
        if w == g.team1:
            rows[g.team1].wins += 1
            rows[g.team2].losses += 1
        elif w == g.team2:
            rows[g.team2].wins += 1
            rows[g.team1].losses += 1

    def record_key(tid: str) -> tuple[int, int]:
        r = rows[tid]
        return (-r.wins, r.losses)

    sorted_by_record = sorted(team_ids, key=record_key)
    groups: list[list[str]] = []
    current: list[str] = []
    current_key = None
    for tid in sorted_by_record:
        k = record_key(tid)
        if current_key is None or k == current_key:
            current.append(tid)
            current_key = k
        else:
            groups.append(current)
            current = [tid]
            current_key = k
    if current:
        groups.append(current)

    trace: list[TieBreakTrace] = []
    ordered: list[str] = []
    for grp in groups:
        if len(grp) == 1:
            ordered.extend(grp)
        else:
            ordered.extend(order_teams(grp, effective_games, start_rule=2, trace=trace))

    return PoolStanding(
        pool=pool,
        ordered_team_ids=ordered,
        rows=rows,
        tiebreak_trace=[_trace_to_dict(t) for t in trace],
    )


def _trace_to_dict(t: TieBreakTrace) -> dict:
    return {
        "rule": t.rule,
        "tied_team_ids": list(t.tied_team_ids),
        "metric_values": t.metric_values,
        "outcome": t.outcome,
        "note": t.note,
    }
