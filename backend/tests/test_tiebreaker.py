"""
Tests for the USAU tiebreaker engine.

Each test corresponds to a canonical example from pages 6-7 of the
"UPA Manual of Championship Series Tournament Formats" tiebreaker section.
"""
from __future__ import annotations

from app.engine.standings import compute_pool_standing
from app.engine.tiebreaker import order_teams
from app.models import Game


def _gf(team1: str, team2: str, s1: int, s2: int, pool: str = "X") -> Game:
    """Final game shorthand."""
    return Game(
        game_id=f"{team1}-{team2}",
        pool=pool,
        team1=team1, team2=team2,
        score1=s1, score2=s2,
        status="final",
    )


# ----------------------- Example 2.1 (head-to-head) ----------------------- #

def test_example_2_1_head_to_head_two_way():
    """A and B are tied 4-2; A beat B -> A finishes ahead."""
    games = [
        _gf("A", "B", 15, 12),
        # filler games to make the 4-2 records (not used by tiebreaker)
        _gf("A", "C", 15, 10), _gf("A", "D", 15, 10), _gf("A", "E", 15, 10),
        _gf("B", "C", 15, 10), _gf("B", "D", 15, 10), _gf("B", "E", 15, 10),
    ]
    result = order_teams(["A", "B"], games, start_rule=2)
    assert result == ["A", "B"]


# ------------------ Example 2.2 (multi-team via record only) ------------------ #

def test_example_2_2_three_way_resolved_by_wl_among_tied():
    """A beat B and C, B beat C -> A, B, C."""
    games = [
        _gf("A", "B", 15, 10),
        _gf("A", "C", 15, 11),
        _gf("B", "C", 15, 13),
    ]
    result = order_teams(["A", "B", "C"], games, start_rule=2)
    assert result == ["A", "B", "C"]


# -------------------------- Example 2.3 (cycle) -------------------------- #

def test_example_2_3_three_way_cycle_falls_through_to_rule_3():
    """A>B, B>C, C>A -- all 1-1 among tied. Must use point diff."""
    games = [
        _gf("A", "B", 15, 10),
        _gf("B", "C", 15, 12),
        _gf("C", "A", 15, 13),
    ]
    result = order_teams(["A", "B", "C"], games, start_rule=2)
    # A: +5 -2 = +3 ; B: -5+3=-2 ; C: +2-3=-1   -> A, C, B
    assert result == ["A", "C", "B"]


# ----------------- Example 3.1 (Rule 3 resolves three-way) ----------------- #

def test_example_3_1_pd_among_tied_full_resolution():
    """The classic +3 / -1 / -2 example from the manual."""
    games = [
        _gf("A", "B", 15, 10),   # A +5
        _gf("B", "C", 15, 12),   # B +3 vs C
        _gf("C", "A", 15, 13),   # C +2 vs A
    ]
    # A: +5 + (-2) = +3
    # B: -5 + (+3) = -2
    # C: -3 + (+2) = -1
    # Order: A, C, B
    assert order_teams(["A", "B", "C"], games, start_rule=2) == ["A", "C", "B"]


# --------- Example 3.2 (Rule 1b - subgroup recurses to Rule 2) --------- #

def test_example_3_2_subgroup_recursion():
    """
    A beat B 15-11, B beat C 15-12, C beat A 15-13.
       A: +4 + -2 = +2
       B: -4 + +3 = -1
       C: -3 + +2 = -1
    Rule 3 splits A out as 1st; B and C remain tied. Per Rule 1b we
    re-enter at Rule 2 for {B, C}, which is head-to-head: B beat C.
    Final order: A, B, C.
    """
    games = [
        _gf("A", "B", 15, 11),
        _gf("B", "C", 15, 12),
        _gf("C", "A", 15, 13),
    ]
    assert order_teams(["A", "B", "C"], games, start_rule=2) == ["A", "B", "C"]


# ---------- Example 3.3 (all PDs zero, advance to Rule 4) ---------- #

def test_example_3_3_rule3_inconclusive_advance_to_rule4():
    """A>B 15-13, B>C 16-14, C>A 15-13 -> all PDs are 0. Need Rule 4."""
    games = [
        _gf("A", "B", 15, 13),
        _gf("B", "C", 16, 14),
        _gf("C", "A", 15, 13),
        # Common opponent D:
        _gf("A", "D", 15, 9),
        _gf("B", "D", 15, 7),
        _gf("C", "D", 15, 12),
    ]
    # Rule 4 PDs vs D: A +6, B +8, C +3 -> B, A, C
    assert order_teams(["A", "B", "C"], games, start_rule=2) == ["B", "A", "C"]


# ----------- Example 4.1 (Rule 4 cleanly resolves three-way) ----------- #

def test_example_4_1_pd_common_opponents():
    games = [
        _gf("A", "B", 15, 13),
        _gf("B", "C", 16, 14),
        _gf("C", "A", 15, 13),
        _gf("A", "D", 15, 9),
        _gf("B", "D", 15, 7),
        _gf("C", "D", 15, 12),
    ]
    assert order_teams(["A", "B", "C"], games, start_rule=2) == ["B", "A", "C"]


# ----------- Example 4.2 (Rule 4a: average multiple meetings) ----------- #

def test_example_4_2_average_multiple_meetings():
    """Same as 4.1 but B beat D twice. The two games should be averaged
    (15-7 and 15-12 -> 15-9.5) so B's PD vs D becomes +5.5, not +11."""
    games = [
        _gf("A", "B", 15, 13),
        _gf("B", "C", 16, 14),
        _gf("C", "A", 15, 13),
        _gf("A", "D", 15, 9),
        _gf("B", "D", 15, 7),
        _gf("B", "D", 15, 12),
        _gf("C", "D", 15, 12),
    ]
    # A: +6 ; B: avg(+8, +3) = +5.5 ; C: +3 -> A, B, C
    assert order_teams(["A", "B", "C"], games, start_rule=2) == ["A", "B", "C"]


# ------------------- Integration: full pool standing ------------------- #

def test_pool_standing_2026_pool_a_day_one_state():
    """The actual state of Pool A after Day 1 of the 2026 D-I Men's Nationals.

    Day-1 results (scraped from play.usaultimate.org):
       Oregon beat Utah 15-11
       Texas lost to Georgia Tech 12-13
       Oregon beat UCSC 15-9
       Texas beat Utah 14-9
       UCSC beat Georgia Tech 15-10

    Standings should be:
       Oregon 2-0   (clear 1st)
       UCSC, Georgia Tech, Texas all 1-1
       Utah 0-2     (clear 5th)

    Among the three 1-1 teams: UCSC beat GT, GT beat Texas, Texas beat Utah
    (Utah is not tied). H2H among tied: UCSC 1-0, GT 1-1, Texas 0-1.
    Rule 2 alone is enough -> UCSC, GT, Texas.
    """
    games = [
        _gf("oregon",       "utah",         15, 11, pool="A"),
        _gf("texas",        "georgia-tech", 12, 13, pool="A"),
        _gf("oregon",       "ucsc",         15,  9, pool="A"),
        _gf("texas",        "utah",         14,  9, pool="A"),
        _gf("ucsc",         "georgia-tech", 15, 10, pool="A"),
    ]
    teams = ["oregon", "ucsc", "georgia-tech", "texas", "utah"]
    ps = compute_pool_standing("A", teams, games)
    assert ps.ordered_team_ids == [
        "oregon", "ucsc", "georgia-tech", "texas", "utah"
    ]
