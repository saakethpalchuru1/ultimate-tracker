"""
Core data models. Pure dataclasses (no Pydantic dep needed for the engine layer)
so the tiebreaker logic stays trivially testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass(frozen=True)
class Team:
    id: str          # canonical id, e.g. "texas"
    name: str        # display name, e.g. "Texas"
    seed: int        # overall tournament seed
    pool: str        # e.g. "A"


@dataclass(frozen=True)
class Game:
    """One pool-play game. Status is 'final' or 'scheduled' or 'in_progress'."""
    game_id: str
    pool: str
    team1: str       # team id
    team2: str       # team id
    score1: Optional[int]
    score2: Optional[int]
    status: str      # final | in_progress | scheduled
    scheduled_at: Optional[str] = None   # ISO8601
    field: Optional[str] = None

    @property
    def is_final(self) -> bool:
        return self.status == "final"

    @property
    def winner(self) -> Optional[str]:
        if not self.is_final or self.score1 is None or self.score2 is None:
            return None
        if self.score1 > self.score2:
            return self.team1
        if self.score2 > self.score1:
            return self.team2
        return None  # tie (should never happen in ultimate)

    @property
    def loser(self) -> Optional[str]:
        w = self.winner
        if w is None:
            return None
        return self.team2 if w == self.team1 else self.team1


@dataclass
class StandingRow:
    team_id: str
    wins: int = 0
    losses: int = 0
    pf: int = 0          # points for, across all final games in pool
    pa: int = 0          # points against
    @property
    def pd(self) -> int:
        return self.pf - self.pa


@dataclass
class PoolStanding:
    pool: str
    ordered_team_ids: list[str]              # final pool order, 1st -> last
    rows: dict[str, StandingRow]             # team_id -> row
    tiebreak_trace: list[dict] = field(default_factory=list)
    """List of trace records explaining how each tie was broken."""


@dataclass
class Pool:
    name: str          # "A", "B", "C", "D"
    team_ids: list[str]


@dataclass
class Tournament:
    id: str
    name: str
    division: str
    pools: list[Pool]
    teams: list[Team]
    games: list[Game]
    bracket_id: str    # "17.4" for 20-team
    target_team_id: Optional[str] = None  # the "favorite team" focus, e.g. "texas"

    def team(self, tid: str) -> Team:
        for t in self.teams:
            if t.id == tid:
                return t
        raise KeyError(tid)

    def games_in_pool(self, pool: str) -> list[Game]:
        return [g for g in self.games if g.pool == pool]
