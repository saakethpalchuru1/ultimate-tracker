"""Tests for the scenario enumerator."""
from __future__ import annotations

from app.engine.scenarios import enumerate_pool_scenarios
from app.models import Game


def _gf(team1, team2, s1, s2, pool="A", status="final"):
    return Game(
        game_id=f"{team1}-{team2}",
        pool=pool,
        team1=team1, team2=team2,
        score1=s1, score2=s2,
        status=status,
    )


def _gs(team1, team2, pool="A"):
    """Scheduled (unplayed) game."""
    return Game(
        game_id=f"sched-{team1}-{team2}",
        pool=pool,
        team1=team1, team2=team2,
        score1=None, score2=None,
        status="scheduled",
    )


def test_enumerates_2_to_n_permutations():
    teams = ["a", "b", "c"]
    games = [
        _gf("a", "b", 15, 10),    # final
        _gs("a", "c"),            # scheduled
        _gs("b", "c"),            # scheduled
    ]
    out = enumerate_pool_scenarios("A", teams, games)
    assert out["n_remaining"] == 2
    assert out["n_permutations"] == 4  # 2^2


def test_target_finish_distribution():
    teams = ["a", "b", "c"]
    games = [
        _gf("a", "b", 15, 10),     # a already has one win
        _gs("a", "c"),
        _gs("b", "c"),
    ]
    out = enumerate_pool_scenarios("A", teams, games, target_team_id="a")
    finishes = sorted({p["target_finish"] for p in out["permutations"]})
    # a has a locked-in win vs b, so a can finish 1st or 2nd but never 3rd
    assert finishes == [1, 2]
    # At least one scenario where a wins out -> 1st
    assert 1 in finishes
