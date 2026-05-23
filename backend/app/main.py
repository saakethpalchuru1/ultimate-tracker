"""
FastAPI app + APScheduler job.

The job runs every SCRAPE_INTERVAL_SECONDS:
  1. Fetch the USAU schedule page (Playwright)
  2. Parse it into Game objects
  3. Compute pool standings (with tiebreaker engine)
  4. Enumerate Pool A scenarios for Texas
  5. Project the bracket
  6. Write three JSON files to OUT_DIR: current.json, scenarios.json, bracket.json

FastAPI serves the same JSON over HTTP for convenience (the frontend can
hit `/api/current.json` directly).
"""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import config, store
from .engine.bracket import project_bracket
from .engine.scenarios import enumerate_pool_scenarios, summarize_target_paths
from .engine.standings import compute_pool_standing
from .models import Game
from .scraper.usau import fetch_page_text, parse_schedule_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ultimate-tracker")

app = FastAPI(title="Ultimate Tracker API")
scheduler = AsyncIOScheduler()
_last_run: dict = {"ok": False, "error": None, "ran_at": None}


@app.on_event("startup")
async def on_startup():
    scheduler.add_job(run_pipeline_safe, "interval", seconds=config.SCRAPE_INTERVAL_SECONDS,
                      next_run_time=None, id="scrape", max_instances=1, coalesce=True)
    scheduler.start()
    # Kick off an immediate run on startup so the dashboard is populated.
    await run_pipeline_safe()


@app.get("/healthz")
async def healthz():
    return {"ok": True, "last_run": _last_run}


@app.post("/refresh")
async def manual_refresh():
    """Manual trigger -- useful when sitting on the sideline."""
    await run_pipeline_safe()
    if not _last_run["ok"]:
        raise HTTPException(500, detail=_last_run.get("error"))
    return _last_run


@app.get("/api/{filename}")
async def serve_snapshot(filename: str):
    if not filename.endswith(".json"):
        raise HTTPException(404)
    p: Path = config.OUT_DIR / filename
    if not p.exists():
        raise HTTPException(404, detail=f"{filename} not yet generated")
    return JSONResponse(content=__import__("json").loads(p.read_text(encoding="utf-8")))


async def run_pipeline_safe():
    try:
        run_pipeline()
        _last_run.update(ok=True, error=None, ran_at=store.utcnow_iso())
        log.info("pipeline ok")
    except Exception as e:
        _last_run.update(ok=False, error=str(e), ran_at=store.utcnow_iso())
        log.error("pipeline failed: %s\n%s", e, traceback.format_exc())


def run_pipeline():
    """The main compute pipeline. Pure, no awaiting needed."""
    tournament = store.load_tournament()
    raw = json_path = None

    # 1. Scrape
    url = "https://play.usaultimate.org/events/2026-D-I-College-Championships/schedule/Men/CollegeMen/"
    page_text = fetch_page_text(url)

    teams_by_name = {t.name: t for t in tournament.teams}
    games: list[Game] = parse_schedule_text(page_text, teams_by_name)
    log.info("parsed %d games", len(games))
    tournament.games = games

    # 2. Pool standings
    pool_standings = {}
    standings_payload = []
    for pool in tournament.pools:
        ps = compute_pool_standing(pool.name, pool.team_ids, games)
        pool_standings[pool.name] = ps.ordered_team_ids
        standings_payload.append({
            "pool": pool.name,
            "ordered_team_ids": ps.ordered_team_ids,
            "rows": {tid: {
                "team_id": tid,
                "wins": ps.rows[tid].wins,
                "losses": ps.rows[tid].losses,
                "pf": ps.rows[tid].pf,
                "pa": ps.rows[tid].pa,
                "pd": ps.rows[tid].pd,
            } for tid in ps.rows},
            "tiebreak_trace": ps.tiebreak_trace,
        })

    # 3. Scenarios (focus pool first; other pools enumerated lightly)
    target = tournament.target_team_id
    target_team = tournament.team(target) if target else None
    target_pool = target_team.pool if target_team else None

    scenarios_payload = {"pools": {}}
    for pool in tournament.pools:
        # Heavy enumeration for the target's pool, light for others (cap perms)
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

    # 4. Bracket projection
    bracket_payload = project_bracket(pool_standings, tournament.bracket_id, target_team_id=target)

    # 5. Write snapshots
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
    store.write_snapshot("current.json", current)
    store.write_snapshot("scenarios.json", scenarios_payload)
    store.write_snapshot("bracket.json", bracket_payload)
