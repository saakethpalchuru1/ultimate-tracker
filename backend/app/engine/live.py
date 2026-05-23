"""
Live in-game margin extrapolation.

The dashboard's most important sideline question:

  "Texas is currently up 10-8 on UCSC. UCSC is up 9-7 on Utah in the
   other simultaneous game. What does Texas need to do RIGHT NOW to
   secure 2nd place in Pool A?"

This module answers that for every in-progress game involving the target
team. The answer is a structured "margin map":

  For each in-progress game involving target_team:
    For each remaining unfinished game OTHER than this one:
      We freeze in-progress games at their current running scores and
      enumerate W/L outcomes for not-yet-started scheduled games.
    Sweep target's final margin (from -14 to +14) and record the
    finish position the target would achieve.
    Derive thresholds: "minimum final margin to secure finish #X".

The frontend renders these thresholds as natural-language guidance plus
the underlying matrix so the user can drill in.

NOTE: "final margin" here is the absolute final score differential
(target_score - opponent_score). Since the running score is partway
done, the UI translates that into "needs to outscore by N more" --
e.g. if currently up 10-8 and threshold is +3, the team needs to
finish at e.g. 15-12 (still +3) which means scoring 5 more while
giving up no more than 4.
"""
from __future__ import annotations

from itertools import product
from typing import Optional

from ..models import Game
from .standings import compute_pool_standing


# Range of final margins we sweep. Ultimate games go to 15 so margins
# outside ~[-14, +14] aren't physically meaningful in pool play.
MARGIN_SWEEP = list(range(-14, 15))


def compute_live_implications(
    target_team_id: str,
    pool: str,
    team_ids: list[str],
    games: list[Game],
) -> dict:
    pool_games = [g for g in games if g.pool == pool]
    target_live = [
        g for g in pool_games
        if g.status == "in_progress"
        and target_team_id in (g.team1, g.team2)
        and g.score1 is not None
    ]

    out: dict = {
        "target_team_id": target_team_id,
        "target_pool": pool,
        "has_live_games": len(target_live) > 0,
        "live_games": [],
    }

    for live_game in target_live:
        out["live_games"].append(
            _analyze_live_game(target_team_id, pool, team_ids, pool_games, live_game)
        )

    return out


def _analyze_live_game(
    target_team_id: str,
    pool: str,
    team_ids: list[str],
    pool_games: list[Game],
    live_game: Game,
) -> dict:
    is_team1 = live_game.team1 == target_team_id
    opponent_id = live_game.team2 if is_team1 else live_game.team1
    target_current = live_game.score1 if is_team1 else live_game.score2
    opp_current = live_game.score2 if is_team1 else live_game.score1
    current_margin = target_current - opp_current

    # Everything that ISN'T this live target game and isn't already final:
    others_unfinished = [
        g for g in pool_games
        if g.game_id != live_game.game_id and not g.is_final
    ]
    # Split: in-progress with score (frozen) vs scheduled (enumerate W/L)
    others_in_progress = [g for g in others_unfinished if g.status == "in_progress" and g.score1 is not None]
    others_scheduled = [g for g in others_unfinished if not (g.status == "in_progress" and g.score1 is not None)]

    finals = [g for g in pool_games if g.is_final]

    matrix: list[dict] = []
    # For each W/L combo of scheduled games:
    for combo in product(*[(g.team1, g.team2) for g in others_scheduled]):
        for margin in MARGIN_SWEEP:
            synthetic = list(finals)
            # freeze in-progress non-target games at current
            for ipg in others_in_progress:
                synthetic.append(Game(
                    game_id=ipg.game_id, pool=ipg.pool,
                    team1=ipg.team1, team2=ipg.team2,
                    score1=ipg.score1, score2=ipg.score2,
                    status="final",
                ))
            # finalize each scheduled game at the assumed winner / default margin
            for og, winner in zip(others_scheduled, combo):
                if winner == og.team1:
                    s1, s2 = 15, 12
                else:
                    s1, s2 = 12, 15
                synthetic.append(Game(
                    game_id=og.game_id, pool=og.pool,
                    team1=og.team1, team2=og.team2,
                    score1=s1, score2=s2, status="final",
                ))
            # finalize THIS live game at the swept margin (keeping running
            # score as the baseline: if currently 10-8 and we want margin +3,
            # final is at e.g. 15-12; if margin -3, final is 12-15)
            if margin >= 0:
                target_final, opp_final = max(target_current, 15), max(target_current, 15) - margin
                if opp_final < opp_current:
                    # impossible: can't take points away
                    continue
            else:
                opp_final, target_final = max(opp_current, 15), max(opp_current, 15) + margin
                if target_final < target_current:
                    continue
            if is_team1:
                s1, s2 = target_final, opp_final
            else:
                s1, s2 = opp_final, target_final
            synthetic.append(Game(
                game_id=live_game.game_id, pool=live_game.pool,
                team1=live_game.team1, team2=live_game.team2,
                score1=s1, score2=s2, status="final",
            ))
            ps = compute_pool_standing(pool, team_ids, synthetic)
            finish = ps.ordered_team_ids.index(target_team_id) + 1
            matrix.append({
                "combo": _label_combo(others_scheduled, combo),
                "target_final_margin": margin,
                "target_finish": finish,
            })

    summary = _summarize_thresholds(matrix, current_margin)

    return {
        "game_id": live_game.game_id,
        "target_team_id": target_team_id,
        "opponent_id": opponent_id,
        "current": {
            "target_score": target_current,
            "opponent_score": opp_current,
            "target_lead_by": current_margin,
        },
        "scheduled_at": live_game.scheduled_at,
        "field": live_game.field,
        "summary": summary,
        "matrix": matrix,
    }


def _label_combo(scheduled: list[Game], combo: tuple) -> str:
    if not scheduled:
        return "(no scheduled games remaining)"
    parts = []
    for g, winner in zip(scheduled, combo):
        loser = g.team2 if winner == g.team1 else g.team1
        parts.append(f"{winner} beats {loser}")
    return "; ".join(parts)


def _summarize_thresholds(matrix: list[dict], current_margin: int) -> list[dict]:
    """For each finish 1..N, find: what's the min target_final_margin that
    achieves it under at least one combo, and is it achievable under ALL
    combos (clinched) or only some (depends on other games)."""
    finishes = sorted({row["target_finish"] for row in matrix})
    out = []
    combos_seen = {row["combo"] for row in matrix}
    for finish in finishes:
        rows_for_finish = [r for r in matrix if r["target_finish"] == finish]
        min_margin = min((r["target_final_margin"] for r in rows_for_finish), default=None)
        # "Clinched at margin M" = at margin M, ALL combos yield <= finish
        clinch_margin: Optional[int] = None
        for m in sorted({r["target_final_margin"] for r in matrix}):
            rows_at_m = [r for r in matrix if r["target_final_margin"] == m]
            if rows_at_m and all(r["target_finish"] <= finish for r in rows_at_m) and len(rows_at_m) == len(combos_seen):
                clinch_margin = m
                break
        out.append({
            "finish": finish,
            "achievable_min_margin": min_margin,
            "guaranteed_at_or_above_margin": clinch_margin,
            "current_margin": current_margin,
            "margin_delta_needed": (clinch_margin - current_margin) if clinch_margin is not None else None,
        })
    return out
