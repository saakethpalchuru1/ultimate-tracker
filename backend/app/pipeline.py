"""
Shared snapshot-building pipeline.

Both scripts/update_snapshots.py (live cron) and scripts/push_fixture.py
(local test harness) feed a list of Game objects into this module and get
back the four JSON file payloads ready to commit to GitHub.

Keeping this isolated from the scraper means we can unit-test the full
pipeline against synthetic game data, and run fixture-mode tests without
touching the network.
"""
from __future__ import annotations

import json

from . import store
from .engine.bracket import project_bracket
from .engine.live import compute_live_implications
from .engine.scenarios import enumerate_pool_scenarios, summarize_target_paths
from .engine.standings import compute_pool_standing
from .models import Game, Tournament


def build_snapshots_from_games(
    tournament: Tournament,
    games: list[Game],
    usau_tie_hints: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    """Compute the four snapshot JSONs given a tournament definition and
    a list of pool-play games. Returns a {path_in_repo -> json_string} dict.
    """
    tournament.games = games
    usau_tie_hints = usau_tie_hints or {}

    target = tournament.target_team_id
    target_team = tournament.team(target) if target else None
    target_pool = target_team.pool if target_team else None

    # 1. Standings (include in-progress = treat running scores as live)
    pool_standings: dict[str, list[str]] = {}
    standings_payload: list[dict] = []
    for pool in tournament.pools:
        ps = compute_pool_standing(pool.name, pool.team_ids, games, include_in_progress=True)
        pool_standings[pool.name] = ps.ordered_team_ids
        standings_payload.append({
            "pool": pool.name,
            "ordered_team_ids": ps.ordered_team_ids,
            "rows": {tid: {
                "team_id": tid, "wins": ps.rows[tid].wins, "losses": ps.rows[tid].losses,
                "pf": ps.rows[tid].pf, "pa": ps.rows[tid].pa, "pd": ps.rows[tid].pd,
            } for tid in ps.rows},
            "tiebreak_trace": ps.tiebreak_trace,
            "usau_tie_hints": usau_tie_hints.get(pool.name, {}),
        })

    # 2. Scenarios (only for not-yet-started games; in-progress games are
    # frozen into the baseline)
    scenarios_payload: dict = {"pools": {}}
    for pool in tournament.pools:
        cap = 1024 if pool.name == target_pool else 64
        sc = enumerate_pool_scenarios(
            pool.name, pool.team_ids, games,
            target_team_id=target if pool.name == target_pool else None,
            max_permutations=cap,
        )
        scenarios_payload["pools"][pool.name] = sc
    if target and target_pool:
        scenarios_payload["target_summary"] = summarize_target_paths(
            scenarios_payload["pools"][target_pool], target
        )

    # 3. Live margins
    if target and target_pool:
        target_pool_obj = next(p for p in tournament.pools if p.name == target_pool)
        live_payload = compute_live_implications(target, target_pool, target_pool_obj.team_ids, games)
    else:
        live_payload = {"has_live_games": False, "live_games": []}

    # 4. Bracket projection
    bracket_payload = project_bracket(pool_standings, tournament.bracket_id, target_team_id=target)

    # 5. Current snapshot
    current = {
        "tournament_id": tournament.id,
        "name": tournament.name,
        "division": tournament.division,
        "target_team_id": tournament.target_team_id,
        "generated_at": store.utcnow_iso(),
        "teams": [t.__dict__ for t in tournament.teams],
        "pools": [{"name": p.name, "team_ids": p.team_ids} for p in tournament.pools],
        "games": [g.__dict__ for g in games],
        "standings": standings_payload,
    }

    return {
        "data/current.json": json.dumps(current, indent=2),
        "data/scenarios.json": json.dumps(scenarios_payload, indent=2),
        "data/bracket.json": json.dumps(bracket_payload, indent=2),
        "data/live.json": json.dumps(live_payload, indent=2),
    }
