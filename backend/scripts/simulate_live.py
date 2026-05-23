"""
Live simulation — pushes a sequence of fixture states 30s apart so you can
watch the dashboard update tick-by-tick.

What it simulates: Saturday 1:00 PM round in Pool A.
  * Background state: all Friday games + Sat 8:30 AM + Sat 10:30 AM games final
  * Two simultaneous live games:
      - Texas vs UCSC  (Pool A 1:00 PM)  -- THE tiebreaker game
      - Oregon vs Georgia Tech (Pool A 1:00 PM)
  * 10 ticks, ~30s apart, total runtime ~5 minutes
  * Scores advance point-by-point through a believable game arc:
      UCSC pulls ahead mid-game then Texas wins 15-12

Usage:
    cd backend
    python -m scripts.simulate_live

Watch the dashboard at https://saakethpalchuru1.github.io/ultimate-tracker/
while the script runs. The Live tab activates immediately; standings,
scenarios, and bracket projection all shift as scores change.

Requires that `git` is on PATH and the local clone is authenticated against
GitHub (which it is, since you've pushed manually already). The script does
'git pull --rebase -X ours' + 'git add data/' + 'git commit' + 'git push'
after each tick.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import store
from app.models import Game
from app.pipeline import build_snapshots_from_games


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"


# ---------- Background state: everything up to the 1:00 PM round ---------- #

def _g(pool, t1, t2, s1, s2, status="final", time_=None, field=None):
    return {
        "pool": pool, "team1": t1, "team2": t2,
        "score1": s1, "score2": s2, "status": status,
        "scheduled_at": time_, "field": field,
    }

BACKGROUND = [
    # ---- Friday Day 1 ---- #
    _g("A","oregon","utah",15,11),
    _g("A","texas","georgia-tech",12,13),
    _g("A","oregon","ucsc",15,9),
    _g("A","texas","utah",14,9),
    _g("A","ucsc","georgia-tech",15,10),
    _g("B","brown","maryland",12,15),
    _g("B","colorado","oregon-state",15,8),
    _g("B","brown","michigan",13,15),
    _g("B","colorado","maryland",15,5),
    _g("B","oregon-state","michigan",13,12),
    _g("C","cal-poly-slo","mcgill",15,7),
    _g("C","carleton","washington",15,10),
    _g("C","penn-state","mcgill",15,8),
    _g("C","carleton","cal-poly-slo",15,10),
    _g("C","penn-state","washington",14,13),
    _g("D","pittsburgh","yale",15,9),
    _g("D","massachusetts","western-washington",15,10),
    _g("D","north-carolina","yale",15,5),
    _g("D","pittsburgh","western-washington",15,11),
    _g("D","north-carolina","massachusetts",10,15),
    # ---- Saturday 8:30 AM finals ---- #
    _g("A","oregon","texas",15,9),
    _g("A","ucsc","utah",15,10),
    _g("B","colorado","michigan",15,11),
    _g("D","north-carolina","pittsburgh",14,15),
    _g("D","massachusetts","yale",15,7),
    # ---- Saturday 10:30 AM finals ---- #
    _g("A","georgia-tech","utah",15,12),
    _g("B","colorado","brown",15,8),
    _g("B","oregon-state","maryland",13,11),
    _g("C","carleton","penn-state",15,13),
    _g("C","cal-poly-slo","washington",15,11),
]


# Live games we'll progress through ticks. Tuples (pool, team1, team2):
LIVE_TEXAS_UCSC  = ("A", "ucsc", "texas")            # opponent first to match USAU
LIVE_OREGON_GT   = ("A", "oregon", "georgia-tech")

# Other 1:00 PM games we leave scheduled or as canned finals
OTHER_100PM = [
    # We'll finalize Pool C's 1:00 PM right away to keep the bracket coherent
    _g("C","carleton","mcgill",15,7),
    # Pool D 1:00 PM games scheduled
    _g("D","massachusetts","pittsburgh",None,None,"scheduled"),
    _g("D","north-carolina","western-washington",None,None,"scheduled"),
    # Pool A/B/C/D 3:00 PM games scheduled (don't care here)
    _g("B","michigan","maryland",None,None,"scheduled"),
    _g("B","oregon-state","brown",None,None,"scheduled"),
    _g("C","washington","mcgill",None,None,"scheduled"),
    _g("C","cal-poly-slo","penn-state",None,None,"scheduled"),
    _g("D","western-washington","yale",None,None,"scheduled"),
]


# Tick-by-tick (score_texas_ucsc, score_oregon_gt, status, description)
# Each entry: (ucsc_score, texas_score, oregon_score, gt_score, status_tx_ucsc, status_or_gt, blurb)
TICKS = [
    ( 0,  0,  0,  0, "in_progress", "in_progress", "Kickoff!  both games tied 0-0"),
    ( 2,  3,  4,  1, "in_progress", "in_progress", "Texas pulls ahead early; Oregon dominant"),
    ( 4,  5,  6,  3, "in_progress", "in_progress", "Trading points"),
    ( 7,  6,  7,  5, "in_progress", "in_progress", "UCSC takes the lead! Texas's path to 2nd narrows"),
    ( 7,  8,  8,  6, "in_progress", "in_progress", "Halftime: Texas 8-7, Oregon 8-6"),
    ( 9,  9,  9,  7, "in_progress", "in_progress", "Tied at 9 - tense"),
    (10, 11, 11,  8, "in_progress", "in_progress", "Texas runs ahead 11-10"),
    (11, 13, 13,  9, "in_progress", "in_progress", "Texas extends to +2; Oregon controlling"),
    (12, 14, 14, 10, "in_progress", "in_progress", "Texas 1 point from clinching 2nd"),
    (12, 15, 15, 11, "final",       "final",       "FINAL: Texas 15-12 (+3, secures 2nd); Oregon 15-11"),
]


def make_games(tick_idx: int) -> list[Game]:
    """Build the full Game list for the given tick."""
    ucsc_s, tx_s, or_s, gt_s, status_tu, status_og, _ = TICKS[tick_idx]
    raws = list(BACKGROUND) + [
        _g(LIVE_TEXAS_UCSC[0], LIVE_TEXAS_UCSC[1], LIVE_TEXAS_UCSC[2], ucsc_s, tx_s,
           status=status_tu, time_="Sat 5/23 1:00 PM", field="202"),
        _g(LIVE_OREGON_GT[0], LIVE_OREGON_GT[1], LIVE_OREGON_GT[2], or_s, gt_s,
           status=status_og, time_="Sat 5/23 1:00 PM", field="210"),
    ] + OTHER_100PM

    games = []
    for i, r in enumerate(raws, 1):
        games.append(Game(
            game_id=f"{r['pool']}-{i:02d}",
            pool=r["pool"], team1=r["team1"], team2=r["team2"],
            score1=r["score1"], score2=r["score2"], status=r["status"],
            scheduled_at=r.get("scheduled_at"), field=r.get("field"),
        ))
    return games


def run_git(*args: str) -> tuple[int, str]:
    """Run a git command in the repo root, return (returncode, combined_output)."""
    r = subprocess.run(["git"] + list(args), cwd=REPO_ROOT,
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    return r.returncode, out


def ensure_clean_start() -> None:
    """Commit any pre-existing uncommitted changes and sync with remote so the
    simulation starts from a clean, fast-forwardable working tree."""
    rc, out = run_git("status", "--porcelain")
    if out.strip():
        print("Working tree had uncommitted changes; staging + committing as 'Pre-SIM WIP':")
        for line in out.splitlines()[:10]:
            print(f"    {line}")
        run_git("add", "-A")
        run_git("commit", "-m", "Pre-SIM WIP")
    # Sync with remote (prefer our copy on conflict)
    rc, out = run_git("pull", "--rebase", "-X", "ours")
    if rc != 0:
        print(f"  pull --rebase warn: {out[:200]}")
    rc, out = run_git("push")
    if rc != 0 and "Everything up-to-date" not in out:
        print(f"  initial push warn: {out[:200]}")


def push_tick(idx: int, blurb: str) -> None:
    # 1. Stage + commit fresh data/ (script wrote them before calling us)
    run_git("add", "-A")
    rc, out = run_git("commit", "-m", f"SIM tick {idx}: {blurb}")
    if rc != 0 and "nothing to commit" not in out.lower() and "nothing added" not in out.lower():
        print(f"  WARN commit returned {rc}: {out[:200]}")
    # 2. Pull rebase (tree is now clean)
    rc, _ = run_git("pull", "--rebase", "-X", "ours")
    # 3. Push, retry once on failure
    rc, out = run_git("push")
    if rc != 0:
        run_git("pull", "--rebase", "-X", "ours")
        rc, out = run_git("push")
        if rc != 0:
            print(f"  PUSH FAILED tick {idx}: {out[:200]}")


def main() -> int:
    tournament = store.load_tournament()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Cleaning pre-existing state...")
    ensure_clean_start()
    print()

    interval = 30
    print(f"Running {len(TICKS)} ticks, ~{interval}s apart (~{interval*len(TICKS)//60} min total)")
    print(f"Dashboard:  https://saakethpalchuru1.github.io/ultimate-tracker/")
    print()

    for idx, tick in enumerate(TICKS):
        ucsc_s, tx_s, or_s, gt_s, st_tu, st_og, blurb = tick
        print(f"[tick {idx+1}/{len(TICKS)}] {blurb}")
        print(f"           UCSC {ucsc_s} - Texas {tx_s} ({st_tu})    "
              f"Oregon {or_s} - GT {gt_s} ({st_og})")

        games = make_games(idx)
        files = build_snapshots_from_games(tournament, games)
        for relpath, content in files.items():
            (DATA_DIR / Path(relpath).name).write_text(content, encoding="utf-8")

        push_tick(idx + 1, blurb)
        print(f"           pushed.  (waiting {interval}s)\n")

        if idx < len(TICKS) - 1:
            time.sleep(interval)

    print("Simulation complete. Dashboard should now show the final Pool A:")
    print("  Oregon 4-0, Texas 2-2 (+1), UCSC 2-2 (+1), GT 2-2 (-5), Utah 0-4")
    print("  Texas projected as A2 -> faces D3 in PQ4 -> potentially Colorado in QF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

