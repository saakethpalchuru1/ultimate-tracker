"""
Local fixture-mode test harness.

Loads a canned game state from backend/fixtures/<name>.json, runs it through
the same pipeline the live cron uses, and writes the four snapshot JSONs to
the repo's data/ folder. From there you commit + push and the dashboard
picks up the change within ~60 seconds (it polls raw.githubusercontent.com).

Usage:
    cd backend
    python -m scripts.push_fixture morning_kickoff
    python -m scripts.push_fixture afternoon_critical
    python -m scripts.push_fixture pool_play_done

Fixture file format (JSON):
    {
      "description": "human-readable scenario name",
      "games": [
        {
          "pool": "A",
          "team1": "oregon", "team2": "utah",
          "score1": 15, "score2": 11,
          "status": "final",              // or "in_progress" or "scheduled"
          "scheduled_at": "Fri 5/22 8:30 AM",
          "field": "202"
        },
        ...
      ]
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import store
from app.models import Game
from app.pipeline import build_snapshots_from_games


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_fixture(name: str) -> tuple[str, list[Game]]:
    path = FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        candidates = sorted(p.stem for p in FIXTURE_DIR.glob("*.json"))
        raise SystemExit(f"fixture '{name}' not found in {FIXTURE_DIR}\navailable: {candidates}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    desc = raw.get("description", name)
    games = []
    for i, g in enumerate(raw["games"], 1):
        games.append(Game(
            game_id=g.get("game_id") or f"{g['pool']}-{i:02d}",
            pool=g["pool"],
            team1=g["team1"],
            team2=g["team2"],
            score1=g.get("score1"),
            score2=g.get("score2"),
            status=g["status"],
            scheduled_at=g.get("scheduled_at"),
            field=g.get("field"),
        ))
    return desc, games


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture", help="fixture name (without .json extension)")
    args = ap.parse_args()

    desc, games = load_fixture(args.fixture)
    tournament = store.load_tournament()
    files = build_snapshots_from_games(tournament, games)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for relpath, content in files.items():
        out = DATA_DIR / Path(relpath).name
        out.write_text(content, encoding="utf-8")
        print(f"  wrote {out}")

    n_final = sum(1 for g in games if g.status == "final")
    n_live  = sum(1 for g in games if g.status == "in_progress")
    n_sched = sum(1 for g in games if g.status == "scheduled")

    print(f"\nFixture: {desc}")
    print(f"Games:   {n_final} final, {n_live} in-progress, {n_sched} scheduled")
    print()
    print("To push this state to GitHub Pages, run:")
    print("    cd ..")
    print("    git pull --rebase")
    print("    git add data/")
    print(f'    git commit -m "TEST: {desc}"')
    print("    git push")
    print()
    print("Dashboard updates ~60s after push (page polls raw.githubusercontent.com).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
