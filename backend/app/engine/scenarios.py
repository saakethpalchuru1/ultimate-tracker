"""
Scenario enumeration for remaining (not-yet-started) pool-play games.

Behavior matrix:
  - "final"        -> contributes to baseline standings
  - "in_progress"  -> FROZEN at its current running score and folded into
                      the baseline (NOT enumerated). The live margin engine
                      in engine/live.py is what answers "what if Texas
                      finishes this in-progress game at margin X".
  - "scheduled"    -> enumerated 2^N over win/loss outcomes

For each binary permutation we synthesize plausible final scores at a
default margin, compute the resulting pool standings, and record:
  * each team's final pool order
  * whether the scenario is "margin sensitive" (the standings flip if we
    re-evaluate at a different default margin -- see MARGIN_PROBES)
"""
from __future__ import annotations

from itertools import product
from typing import Optional

from ..models import Game
from .standings import compute_pool_standing


MARGIN_PROBES = [1, 3, 5, 8, 12]
DEFAULT_MARGIN = 3


def enumerate_pool_scenarios(
    pool: str,
    team_ids: list[str],
    games: list[Game],
    target_team_id: Optional[str] = None,
    max_permutations: int = 256,
) -> dict:
    pool_games = [g for g in games if g.pool == pool]

    final_games: list[Game] = []
    remaining: list[Game] = []
    for g in pool_games:
        if g.is_final:
            final_games.append(g)
        elif g.status == "in_progress" and g.score1 is not None:
            final_games.append(Game(
                game_id=g.game_id, pool=g.pool,
                team1=g.team1, team2=g.team2,
                score1=g.score1, score2=g.score2,
                status="final",
                scheduled_at=g.scheduled_at, field=g.field,
            ))
        else:
            remaining.append(g)

    if len(remaining) > 12:
        remaining = remaining[:12]

    outcomes_per_game = [(g.team1, g.team2) for g in remaining]
    permutations: list[dict] = []
    for idx, choice in enumerate(product(*outcomes_per_game)):
        if idx >= max_permutations:
            break
        assumed = []
        synthetic_games = list(final_games)
        for g, winner_id in zip(remaining, choice):
            loser_id = g.team2 if winner_id == g.team1 else g.team1
            if winner_id == g.team1:
                s1, s2 = 15, 15 - DEFAULT_MARGIN
            else:
                s1, s2 = 15 - DEFAULT_MARGIN, 15
            synthetic_games.append(Game(
                game_id=g.game_id, pool=g.pool,
                team1=g.team1, team2=g.team2,
                score1=s1, score2=s2, status="final",
            ))
            assumed.append({
                "game_id": g.game_id,
                "winner_id": winner_id,
                "loser_id": loser_id,
                "winning_margin": DEFAULT_MARGIN,
            })
        standing = compute_pool_standing(pool, team_ids, synthetic_games)
        order = standing.ordered_team_ids
        margin_sensitive = _is_margin_sensitive(
            pool, team_ids, final_games, remaining, choice, order
        )
        perm_rec = {
            "id": idx,
            "assumed_outcomes": assumed,
            "final_order": order,
            "margin_sensitive": margin_sensitive,
            "tiebreak_trace": standing.tiebreak_trace,
        }
        if target_team_id and target_team_id in order:
            perm_rec["target_finish"] = order.index(target_team_id) + 1
        permutations.append(perm_rec)

    return {
        "pool": pool,
        "n_remaining": len(remaining),
        "n_permutations": len(permutations),
        "permutations": permutations,
    }


def _is_margin_sensitive(
    pool: str,
    team_ids: list[str],
    final_games: list[Game],
    remaining: list[Game],
    winners: tuple,
    baseline_order: list[str],
) -> bool:
    for margin in MARGIN_PROBES:
        if margin == DEFAULT_MARGIN:
            continue
        synthetic = list(final_games)
        for g, winner_id in zip(remaining, winners):
            if winner_id == g.team1:
                s1, s2 = 15, 15 - margin
            else:
                s1, s2 = 15 - margin, 15
            synthetic.append(Game(
                game_id=g.game_id, pool=g.pool,
                team1=g.team1, team2=g.team2,
                score1=s1, score2=s2, status="final",
            ))
        order = compute_pool_standing(pool, team_ids, synthetic).ordered_team_ids
        if order != baseline_order:
            return True
    return False


def summarize_target_paths(scenarios: dict, target_team_id: str) -> dict:
    by_finish: dict[int, list[dict]] = {}
    for p in scenarios["permutations"]:
        if "target_finish" not in p:
            continue
        by_finish.setdefault(p["target_finish"], []).append(p)
    return {
        "target_team_id": target_team_id,
        "finish_distribution": {f: len(v) for f, v in sorted(by_finish.items())},
        "scenarios_by_finish": {str(f): v for f, v in sorted(by_finish.items())},
    }
