"""Live simulation -- pushes a sequence of fixture states 30s apart.

Usage: cd backend && python -m scripts.simulate_live
"""
from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import store
from app.models import Game
from app.pipeline import build_snapshots_from_games

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
REPO_SLUG = "saakethpalchuru1/ultimate-tracker"


def _g(pool, t1, t2, s1, s2, status="final", time_=None, field=None):
    return {"pool": pool, "team1": t1, "team2": t2, "score1": s1, "score2": s2,
            "status": status, "scheduled_at": time_, "field": field}

BACKGROUND = [
    _g("A","oregon","utah",15,11), _g("A","texas","georgia-tech",12,13),
    _g("A","oregon","ucsc",15,9), _g("A","texas","utah",14,9),
    _g("A","ucsc","georgia-tech",15,10),
    _g("B","brown","maryland",12,15), _g("B","colorado","oregon-state",15,8),
    _g("B","brown","michigan",13,15), _g("B","colorado","maryland",15,5),
    _g("B","oregon-state","michigan",13,12),
    _g("C","cal-poly-slo","mcgill",15,7), _g("C","carleton","washington",15,10),
    _g("C","penn-state","mcgill",15,8), _g("C","carleton","cal-poly-slo",15,10),
    _g("C","penn-state","washington",14,13),
    _g("D","pittsburgh","yale",15,9), _g("D","massachusetts","western-washington",15,10),
    _g("D","north-carolina","yale",15,5), _g("D","pittsburgh","western-washington",15,11),
    _g("D","north-carolina","massachusetts",10,15),
    _g("A","oregon","texas",15,9), _g("A","ucsc","utah",15,10),
    _g("B","colorado","michigan",15,11),
    _g("D","north-carolina","pittsburgh",14,15), _g("D","massachusetts","yale",15,7),
    _g("A","georgia-tech","utah",15,12),
    _g("B","colorado","brown",15,8), _g("B","oregon-state","maryland",13,11),
    _g("C","carleton","penn-state",15,13), _g("C","cal-poly-slo","washington",15,11),
]

OTHER_100PM = [
    _g("C","carleton","mcgill",15,7),
    _g("D","massachusetts","pittsburgh",None,None,"scheduled"),
    _g("D","north-carolina","western-washington",None,None,"scheduled"),
    _g("B","michigan","maryland",None,None,"scheduled"),
    _g("B","oregon-state","brown",None,None,"scheduled"),
    _g("C","washington","mcgill",None,None,"scheduled"),
    _g("C","cal-poly-slo","penn-state",None,None,"scheduled"),
    _g("D","western-washington","yale",None,None,"scheduled"),
]

TICKS = [
    ( 0,  0,  0,  0, "in_progress", "in_progress", "Kickoff! both games tied 0-0"),
    ( 2,  3,  4,  1, "in_progress", "in_progress", "Texas pulls ahead early"),
    ( 4,  5,  6,  3, "in_progress", "in_progress", "Trading points"),
    ( 7,  6,  7,  5, "in_progress", "in_progress", "UCSC takes the lead"),
    ( 7,  8,  8,  6, "in_progress", "in_progress", "Halftime: Texas 8-7"),
    ( 9,  9,  9,  7, "in_progress", "in_progress", "Tied at 9 - tense"),
    (10, 11, 11,  8, "in_progress", "in_progress", "Texas runs ahead 11-10"),
    (11, 13, 13,  9, "in_progress", "in_progress", "Texas extends +2"),
    (12, 14, 14, 10, "in_progress", "in_progress", "Texas 1 point from clinching"),
    (12, 15, 15, 11, "final",       "final",       "FINAL Texas 15-12, Oregon 15-11"),
]


def make_games(tick_idx):
    ucsc_s, tx_s, or_s, gt_s, st_tu, st_og, _ = TICKS[tick_idx]
    raws = list(BACKGROUND) + [
        _g("A","ucsc","texas",ucsc_s,tx_s,status=st_tu,time_="Sat 5/23 1:00 PM",field="202"),
        _g("A","oregon","georgia-tech",or_s,gt_s,status=st_og,time_="Sat 5/23 1:00 PM",field="210"),
    ] + OTHER_100PM
    games = []
    for i, r in enumerate(raws, 1):
        games.append(Game(
            game_id=r["pool"] + "-" + str(i).zfill(2),
            pool=r["pool"], team1=r["team1"], team2=r["team2"],
            score1=r["score1"], score2=r["score2"], status=r["status"],
            scheduled_at=r.get("scheduled_at"), field=r.get("field"),
        ))
    return games


def run_git(*args):
    r = subprocess.run(["git"] + list(args), cwd=REPO_ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()



def ensure_clean_start():
    rc, out = run_git("status", "--porcelain")
    if out.strip():
        print("Pre-existing uncommitted changes detected; staging + committing.")
        run_git("add", "-A")
        run_git("commit", "-m", "Pre-SIM WIP")
    run_git("pull", "--rebase", "-X", "ours")
    run_git("push")


def push_tick(idx, blurb):
    run_git("add", "-A")
    rc, out = run_git("commit", "-m", "SIM tick " + str(idx) + ": " + blurb)
    run_git("pull", "--rebase", "-X", "ours")
    rc, out = run_git("push")
    if rc != 0:
        run_git("pull", "--rebase", "-X", "ours")
        rc, out = run_git("push")
        if rc != 0:
            print("  PUSH FAILED tick " + str(idx) + ": " + out[:200])
            return


def main():
    tournament = store.load_tournament()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Cleaning pre-existing state...")
    ensure_clean_start()
    print()
    interval = 30
    print("Running " + str(len(TICKS)) + " ticks, ~" + str(interval) + "s apart")
    print("Dashboard:  https://saakethpalchuru1.github.io/ultimate-tracker/")
    print()
    for idx, tick in enumerate(TICKS):
        ucsc_s, tx_s, or_s, gt_s, st_tu, st_og, blurb = tick
        print("[tick " + str(idx+1) + "/" + str(len(TICKS)) + "] " + blurb)
        print("           UCSC " + str(ucsc_s) + " - Texas " + str(tx_s) + " (" + st_tu + ")    " +
              "Oregon " + str(or_s) + " - GT " + str(gt_s) + " (" + st_og + ")")
        games = make_games(idx)
        files = build_snapshots_from_games(tournament, games)
        for relpath, content in files.items():
            (DATA_DIR / Path(relpath).name).write_text(content, encoding="utf-8")
        push_tick(idx + 1, blurb)
        print("           pushed.  (waiting " + str(interval) + "s)\n")
        if idx < len(TICKS) - 1:
            time.sleep(interval)
    print("Simulation complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
