"""
Live in-game margin extrapolation.

Output schema:
  {
    "target_team_id": "texas",
    "target_pool": "A",
    "has_live_games": true,
    "live_games": [           # games involving the target team
      { ..., summary: [...], matrix: [...] }
    ],
    "other_live_games": [     # in-progress games in the target's pool that don't
                              # involve the target -- shown for context so the user
                              # sees the full live picture across the pool
      {"game_id": "...", "team1": "...", "team2": "...", "score1": 7, "score2": 5,
       "scheduled_at": "...", "field": "..."}
    ]
  }
"""
from __future__ import annotations
from itertools import product
from typing import Optional

from ..models import Game
from .standings import compute_pool_standing

MARGIN_SWEEP = list(range(-14, 15))


def compute_live_implications(target_team_id, pool, team_ids, games):
    pool_games = [g for g in games if g.pool == pool]
    target_live = [
        g for g in pool_games
        if g.status == "in_progress" and target_team_id in (g.team1, g.team2) and g.score1 is not None
    ]
    other_live = [
        g for g in pool_games
        if g.status == "in_progress" and target_team_id not in (g.team1, g.team2) and g.score1 is not None
    ]

    out = {
        "target_team_id": target_team_id,
        "target_pool": pool,
        "has_live_games": len(target_live) > 0 or len(other_live) > 0,
        "live_games": [],
        "other_live_games": [
            {
                "game_id": g.game_id, "team1": g.team1, "team2": g.team2,
                "score1": g.score1, "score2": g.score2,
                "scheduled_at": g.scheduled_at, "field": g.field,
            } for g in other_live
        ],
    }

    for live_game in target_live:
        out["live_games"].append(_analyze_live_game(target_team_id, pool, team_ids, pool_games, live_game))
    return out


def _analyze_live_game(target_team_id, pool, team_ids, pool_games, live_game):
    is_team1 = live_game.team1 == target_team_id
    opponent_id = live_game.team2 if is_team1 else live_game.team1
    target_current = live_game.score1 if is_team1 else live_game.score2
    opp_current = live_game.score2 if is_team1 else live_game.score1
    current_margin = target_current - opp_current

    others_unfinished = [g for g in pool_games if g.game_id != live_game.game_id and not g.is_final]
    others_in_progress = [g for g in others_unfinished if g.status == "in_progress" and g.score1 is not None]
    others_scheduled  = [g for g in others_unfinished if not (g.status == "in_progress" and g.score1 is not None)]
    finals = [g for g in pool_games if g.is_final]

    matrix = []
    for combo in product(*[(g.team1, g.team2) for g in others_scheduled]):
        for margin in MARGIN_SWEEP:
            synthetic = list(finals)
            for ipg in others_in_progress:
                synthetic.append(Game(
                    game_id=ipg.game_id, pool=ipg.pool,
                    team1=ipg.team1, team2=ipg.team2,
                    score1=ipg.score1, score2=ipg.score2, status="final",
                ))
            for og, winner in zip(others_scheduled, combo):
                s1, s2 = (15, 12) if winner == og.team1 else (12, 15)
                synthetic.append(Game(
                    game_id=og.game_id, pool=og.pool,
                    team1=og.team1, team2=og.team2,
                    score1=s1, score2=s2, status="final",
                ))
            # Synthesize this live game's final at the swept margin
            if margin >= 0:
                target_final = max(target_current, 15)
                opp_final = target_final - margin
                if opp_final < opp_current:
                    continue
            else:
                opp_final = max(opp_current, 15)
                target_final = opp_final + margin
                if target_final < target_current:
                    continue
            s1, s2 = (target_final, opp_final) if is_team1 else (opp_final, target_final)
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
                "projected_final_target": target_final,
                "projected_final_opp": opp_final,
            })

    summary = _summarize_thresholds(matrix, current_margin, target_current, opp_current, target_team_id, opponent_id)

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


def _label_combo(scheduled, combo):
    if not scheduled:
        return "(no scheduled games remaining)"
    parts = []
    for g, winner in zip(scheduled, combo):
        loser = g.team2 if winner == g.team1 else g.team1
        parts.append(f"{winner} beats {loser}")
    return "; ".join(parts)


def _summarize_thresholds(matrix, current_margin, target_current, opp_current, target_id, opp_id):
    """Build per-finish guidance in human-readable form.

    For each achievable finish position N:
      - min_winning_margin_needed: smallest +margin that EVER achieves finish N (under at least one combo)
      - guaranteed_at_margin: smallest margin where finish <= N under ALL combos (clinched)
      - human_text: plain-English instruction
      - example_score: a concrete "X-Y" final that secures finish N
    """
    # Only show top-3 finishes (4th/5th are bracket-out, no advancement implication)
    finishes = sorted(f for f in {row["target_finish"] for row in matrix} if f <= 3)
    combos_seen = {row["combo"] for row in matrix}
    out = []
    for finish in finishes:
        rows_for_finish = [r for r in matrix if r["target_finish"] == finish]
        # Cleanest "guaranteed" margin = the smallest margin at which EVERY combo gives finish<=N
        clinch_margin = None
        for m in sorted({r["target_final_margin"] for r in matrix}):
            rows_at_m = [r for r in matrix if r["target_final_margin"] == m]
            if rows_at_m and all(r["target_finish"] <= finish for r in rows_at_m) and len(rows_at_m) == len(combos_seen):
                clinch_margin = m
                break

        # Example final score that clinches: use the smallest matrix row with that margin
        example = None
        if clinch_margin is not None:
            for r in matrix:
                if r["target_final_margin"] == clinch_margin:
                    example = (r["projected_final_target"], r["projected_final_opp"])
                    break

        # Human text
        if clinch_margin is None:
            human = f"Finish #{finish} not guaranteed; depends on other games."
            need_more = None
        elif clinch_margin > 0:
            opp_team = opp_id  # for clarity
            need_more = clinch_margin - current_margin
            if need_more <= 0:
                human = (f"Already locked: at the current score you're projected to finish #{finish}. "
                         f"Just don't lose the lead.")
            else:
                # how many more points must Texas outscore by
                human = (f"Win by {clinch_margin}+ points to lock #{finish}. "
                         f"Currently leading by {current_margin}; outscore opponent by {need_more}+ from now.")
        elif clinch_margin == 0:
            need_more = -current_margin
            human = f"Don't lose this game to lock #{finish} (a draw or any win works)."
        else:
            # clinch_margin negative -> losing by some amount still secures this finish
            loss_buffer = -clinch_margin   # you can lose by up to this much
            need_more = loss_buffer - (-current_margin if current_margin < 0 else 0)
            human = f"Even a loss by {loss_buffer} or less locks #{finish}."

        out.append({
            "finish": finish,
            "guaranteed_at_or_above_margin": clinch_margin,
            "min_winning_margin_needed": clinch_margin if clinch_margin is not None and clinch_margin > 0 else None,
            "current_margin": current_margin,
            "margin_delta_needed": need_more,
            "human_text": human,
            "example_score": example,   # (target_final, opp_final) tuple or None
        })
    return out
