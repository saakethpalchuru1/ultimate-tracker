#!/usr/bin/env python3
"""Zero-dependency engine verification. Exits non-zero on first failure."""
from __future__ import annotations
import sys
from app.engine.bracket import project_bracket
from app.engine.live import compute_live_implications
from app.engine.scenarios import enumerate_pool_scenarios
from app.engine.standings import compute_pool_standing
from app.engine.tiebreaker import order_teams
from app.models import Game

PASS = 0
FAIL = 0

def check(name, actual, expected):
    global PASS, FAIL
    if actual == expected:
        print(f"  OK   {name}"); PASS += 1
    else:
        print(f"  FAIL {name}\n        expected: {expected!r}\n        actual:   {actual!r}"); FAIL += 1

def truthy(name, condition, hint=""):
    global PASS, FAIL
    if condition:
        print(f"  OK   {name}"); PASS += 1
    else:
        print(f"  FAIL {name}  {hint}"); FAIL += 1

def gf(t1, t2, s1, s2, pool="X"):
    return Game(game_id=f"{t1}-{t2}", pool=pool, team1=t1, team2=t2, score1=s1, score2=s2, status="final")

def gs(t1, t2, pool="X"):
    return Game(game_id=f"sched-{t1}-{t2}", pool=pool, team1=t1, team2=t2, score1=None, score2=None, status="scheduled")

def gip(t1, t2, s1, s2, pool="X"):
    return Game(game_id=f"live-{t1}-{t2}", pool=pool, team1=t1, team2=t2, score1=s1, score2=s2, status="in_progress")

print("Tiebreaker engine (USAU canonical examples)")
check("2.1", order_teams(["A","B"], [gf("A","B",15,12)], 2), ["A","B"])
check("2.2", order_teams(["A","B","C"], [gf("A","B",15,10),gf("A","C",15,11),gf("B","C",15,13)], 2), ["A","B","C"])
check("2.3 / 3.1 cycle PD", order_teams(["A","B","C"], [gf("A","B",15,10),gf("B","C",15,12),gf("C","A",15,13)], 2), ["A","C","B"])
check("3.2 Rule 1b recursion", order_teams(["A","B","C"], [gf("A","B",15,11),gf("B","C",15,12),gf("C","A",15,13)], 2), ["A","B","C"])
check("3.3 -> 4.1 common opponents", order_teams(["A","B","C"],
      [gf("A","B",15,13),gf("B","C",16,14),gf("C","A",15,13),gf("A","D",15,9),gf("B","D",15,7),gf("C","D",15,12)], 2),
      ["B","A","C"])
check("4.2 average multi-meetings", order_teams(["A","B","C"],
      [gf("A","B",15,13),gf("B","C",16,14),gf("C","A",15,13),gf("A","D",15,9),
       gf("B","D",15,7),gf("B","D",15,12),gf("C","D",15,12)], 2),
      ["A","B","C"])

print("\nPool A 2026 Day 1 standings")
pool_a = [
    gf("oregon","utah",15,11,pool="A"),
    gf("texas","georgia-tech",12,13,pool="A"),
    gf("oregon","ucsc",15,9,pool="A"),
    gf("texas","utah",14,9,pool="A"),
    gf("ucsc","georgia-tech",15,10,pool="A"),
]
team_ids = ["oregon","ucsc","georgia-tech","texas","utah"]
check("Pool A end of Day 1",
      compute_pool_standing("A", team_ids, pool_a).ordered_team_ids,
      ["oregon","ucsc","georgia-tech","texas","utah"])

print("\nScenario enumerator")
sc = enumerate_pool_scenarios("A", ["a","b","c"], [gf("a","b",15,10,pool="A"), gs("a","c",pool="A"), gs("b","c",pool="A")], target_team_id="a")
check("permutations = 2^N", sc["n_permutations"], 4)
check("finish distribution", sorted({p["target_finish"] for p in sc["permutations"]}), [1,2])

sc2 = enumerate_pool_scenarios("A", ["a","b","c"], [gf("a","b",15,10,pool="A"), gip("a","c",13,8,pool="A"), gs("b","c",pool="A")], target_team_id="a")
check("in-progress frozen, not enumerated", sc2["n_permutations"], 2)

print("\nLive margin engine (Saturday afternoon snapshot)")
sat = [
    gf("oregon","utah",15,11,pool="A"),
    gf("texas","georgia-tech",12,13,pool="A"),
    gf("oregon","ucsc",15,9,pool="A"),
    gf("texas","utah",14,9,pool="A"),
    gf("ucsc","georgia-tech",15,10,pool="A"),
    gf("oregon","texas",15,9,pool="A"),
    gf("ucsc","utah",15,10,pool="A"),
    gf("georgia-tech","utah",15,12,pool="A"),
    gip("texas","ucsc",8,6,pool="A"),
    gs("oregon","georgia-tech",pool="A"),
]
live = compute_live_implications("texas","A", team_ids, sat)
truthy("has_live_games", live["has_live_games"] is True)
truthy("one live game", len(live["live_games"]) == 1)
lg = live["live_games"][0]
check("opponent", lg["opponent_id"], "ucsc")
check("current score captured",
      (lg["current"]["target_score"], lg["current"]["opponent_score"], lg["current"]["target_lead_by"]),
      (8, 6, 2))
truthy("summary present", len(lg["summary"]) >= 2)
truthy("matrix non-empty", len(lg["matrix"]) > 0)

print("\nBracket projector")
pool_standings = {
    "A":["oregon","ucsc","georgia-tech","texas","utah"],
    "B":["colorado","oregon-state","maryland","michigan","brown"],
    "C":["carleton","penn-state","cal-poly-slo","washington","mcgill"],
    "D":["pittsburgh","massachusetts","north-carolina","western-washington","yale"],
}
br = project_bracket(pool_standings, "17.4", target_team_id="texas")
check("rounds", [r["name"] for r in br["rounds"]], ["Prequarterfinals","Quarterfinals","Semifinals","Final"])
qf = next(r for r in br["rounds"] if r["name"]=="Quarterfinals")
pool1 = {p["team_id"] for g in qf["games"] for p in g["participants"] if p["team_id"] and p["source"].endswith("#1")}
check("pool winners -> QF", pool1, {"oregon","colorado","carleton","pittsburgh"})

print("\ninclude_in_progress flag")
mid = [gf("a","b",15,10,pool="A"), gip("a","c",14,13,pool="A")]
strict = compute_pool_standing("A", ["a","b","c"], mid, include_in_progress=False)
livem  = compute_pool_standing("A", ["a","b","c"], mid, include_in_progress=True)
truthy("strict: a 1-0", strict.rows["a"].wins == 1)
truthy("live: a 2-0", livem.rows["a"].wins == 2)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
