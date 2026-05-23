"""Smoke tests for the bracket projector."""
from __future__ import annotations

from app.engine.bracket import project_bracket


def test_projector_consumes_pool_standings():
    pool_standings = {
        "A": ["oregon", "ucsc", "georgia-tech", "texas", "utah"],
        "B": ["colorado", "oregon-state", "maryland", "michigan", "brown"],
        "C": ["carleton", "penn-state", "cal-poly-slo", "washington", "mcgill"],
        "D": ["pittsburgh", "massachusetts", "north-carolina", "western-washington", "yale"],
    }
    out = project_bracket(pool_standings, bracket_id="17.4", target_team_id="texas")
    assert out["bracket_id"] == "17.4"
    round_names = [r["name"] for r in out["rounds"]]
    assert "Prequarterfinals" in round_names
    assert "Quarterfinals" in round_names
    assert "Semifinals" in round_names
    assert "Final" in round_names
    # Texas should appear in the projected path (Pool A #4 misses the bracket,
    # so target_path may be empty -- but the field must exist).
    assert "target_path" in out


def test_pool_winners_go_to_quarters():
    pool_standings = {
        "A": ["oregon", "ucsc", "georgia-tech", "texas", "utah"],
        "B": ["colorado", "oregon-state", "maryland", "michigan", "brown"],
        "C": ["carleton", "penn-state", "cal-poly-slo", "washington", "mcgill"],
        "D": ["pittsburgh", "massachusetts", "north-carolina", "western-washington", "yale"],
    }
    out = project_bracket(pool_standings)
    quarters = next(r for r in out["rounds"] if r["name"] == "Quarterfinals")
    teams_in_quarters = []
    for g in quarters["games"]:
        for p in g["participants"]:
            if p["team_id"] and p["source"].startswith("Pool"):
                teams_in_quarters.append(p["team_id"])
    assert set(teams_in_quarters) == {"oregon", "colorado", "carleton", "pittsburgh"}


def test_prequarter_pairings_use_2_vs_3():
    pool_standings = {
        "A": ["oregon", "ucsc", "georgia-tech", "texas", "utah"],
        "B": ["colorado", "oregon-state", "maryland", "michigan", "brown"],
        "C": ["carleton", "penn-state", "cal-poly-slo", "washington", "mcgill"],
        "D": ["pittsburgh", "massachusetts", "north-carolina", "western-washington", "yale"],
    }
    out = project_bracket(pool_standings)
    pq = next(r for r in out["rounds"] if r["name"] == "Prequarterfinals")
    pq_team_ids = {p["team_id"] for g in pq["games"] for p in g["participants"]}
    # All four 2nd-place finishers + all four 3rd-place finishers
    expected = {
        "ucsc", "oregon-state", "penn-state", "massachusetts",   # 2nd
        "georgia-tech", "maryland", "cal-poly-slo", "north-carolina",  # 3rd
    }
    assert pq_team_ids == expected
