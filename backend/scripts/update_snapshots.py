"""
Render cron entry-point.

This script:
  1. Checks the run-window (default: Sat 8:30am - 8:00pm America/Chicago,
     since the 2026 D-I Men's tournament is in Rockford, IL).
  2. Fetches the USAU schedule HTML via plain HTTP.
  3. Parses pool play games (including in-progress live scores).
  4. Computes standings, scenarios, live margins, and bracket projection.
  5. Pushes the four JSON files to GitHub so GitHub Pages serves them.

Configure Render's cron schedule generously (every 5 minutes); the
RUN_WINDOW gate inside this script is what actually limits work to game
hours so we don't burn quota during the night.

Env vars:
  GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH    -- see scripts/github_push.py
  RUN_WINDOW_TZ        -- IANA tz, default "America/Chicago"
  RUN_WINDOW_START     -- "HH:MM", default "08:30"
  RUN_WINDOW_END       -- "HH:MM", default "20:00"
  RUN_WINDOW_DAYS      -- comma-separated weekday names; default "Sat,Sun"
  ALLOW_ANY_TIME=1     -- bypass the gate (useful for manual triggers)
  TOURNAMENT_FILE      -- override which tournament definition to use
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Make the `app` package importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, store
from app.engine.bracket import project_bracket
from app.engine.live import compute_live_implications
from app.engine.scenarios import enumerate_pool_scenarios, summarize_target_paths
from app.engine.standings import compute_pool_standing
from app.scraper.usau import fetch_html, parse_schedule_html
from scripts.github_push import push_files

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("update_snapshots")

USAU_URL = (
    "https://play.usaultimate.org/events/2026-D-I-College-Championships/"
    "schedule/Men/CollegeMen/?ViewAll=true&bracket=true"
)


def in_run_window() -> tuple[bool, str]:
    if os.environ.get("ALLOW_ANY_TIME") == "1":
        return True, "ALLOW_ANY_TIME=1"
    tz = ZoneInfo(os.environ.get("RUN_WINDOW_TZ", "America/Chicago"))
    now = datetime.now(tz)

    days_env = os.environ.get("RUN_WINDOW_DAYS", "Sat,Sun")
    allowed_days = {d.strip().lower()[:3] for d in days_env.split(",")}
    if now.strftime("%a").lower()[:3] not in allowed_days:
        return False, f"day {now.strftime('%a')} not in allowed {sorted(allowed_days)}"

    start_h, start_m = (int(x) for x in os.environ.get("RUN_WINDOW_START", "08:30").split(":"))
    end_h, end_m = (int(x) for x in os.environ.get("RUN_WINDOW_END", "20:00").split(":"))
    start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if not (start <= now <= end):
        return False, f"local time {now.strftime('%H:%M')} outside [{start_h:02d}:{start_m:02d}, {end_h:02d}:{end_m:02d}]"
    return True, f"in window ({now.isoformat()})"


def build_snapshots() -> dict[str, str]:
    tournament = store.load_tournament()
    log.info("loaded tournament: %s (target=%s)", tournament.name, tournament.target_team_id)

    html = fetch_html(USAU_URL)
    teams_by_name = {t.name: t for t in tournament.teams}
    games, usau_tie_hints = parse_schedule_html(html, teams_by_name)
    log.info("parsed %d games (%d final, %d in-progress, %d scheduled)",
             len(games),
             sum(1 for g in games if g.status == "final"),
             sum(1 for g in games if g.status == "in_progress"),
             sum(1 for g in games if g.status == "scheduled"))
    tournament.games = games

    target = tournament.target_team_id
    target_team = tournament.team(target) if target else None
    target_pool = target_team.pool if target_team else None

    # ---- standings (include in-progress so live games push the standings live) ---- #
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

    # ---- scenarios (only for not-yet-started games) ---- #
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

    # ---- live margins (the new piece) ---- #
    if target and target_pool:
        target_pool_obj = next(p for p in tournament.pools if p.name == target_pool)
        live_payload = compute_live_implications(target, target_pool, target_pool_obj.team_ids, games)
    else:
        live_payload = {"has_live_games": False, "live_games": []}

    # ---- bracket projection ---- #
    bracket_payload = project_bracket(pool_standings, tournament.bracket_id, target_team_id=target)

    # ---- current snapshot ---- #
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


def main() -> int:
    ok, reason = in_run_window()
    if not ok:
        log.info("skipping: %s", reason)
        return 0
    log.info("in window: %s", reason)

    try:
        files = build_snapshots()
    except Exception:
        log.exception("snapshot build failed")
        return 1

    if os.environ.get("DRY_RUN") == "1" or not os.environ.get("GITHUB_TOKEN"):
        # Local dev: write to backend/../data/ instead of pushing
        out_dir = Path(__file__).resolve().parent.parent.parent / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        for relpath, content in files.items():
            (out_dir / Path(relpath).name).write_text(content, encoding="utf-8")
        log.info("dry-run: wrote %d files to %s", len(files), out_dir)
        return 0

    push_files(files, commit_message=f"live update {store.utcnow_iso()}")
    log.info("pushed %d files to %s", len(files), os.environ.get("GITHUB_REPO"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
