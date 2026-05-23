"""
Bracket projection for the official USAU 20-team "Bracket 17.4" format:
  - 4 pools of 5 teams
  - Pool 1st place teams advance directly to quarterfinals (4 teams)
  - Pool 2nd and 3rd place teams play prequarters (8 teams)
  - 4 prequarter winners advance to quarters (8 teams total in quarters)
  - 4 quarter winners advance to semis
  - 2 semi winners advance to final

The exact prequarter / quarter crossover mapping is loaded from
backend/app/data/bracket_17_4.json so it can be tweaked without code changes
when USAU publishes the official year-specific crossovers.

Output schema is a flat list of "slots" -- each slot is a bracket position
that either references a projected team (if pool standings determine it) or
a TBD/source reference (if it depends on another bracket game).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_bracket_definition(bracket_id: str = "17.4") -> dict:
    p = DATA_DIR / f"bracket_{bracket_id.replace('.', '_')}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def project_bracket(
    pool_standings: dict[str, list[str]],   # pool -> ordered team ids
    bracket_id: str = "17.4",
    target_team_id: Optional[str] = None,
) -> dict:
    """
    Returns a projected bracket structure:
        {
          "bracket_id": "17.4",
          "rounds": [
             {"name": "Prequarters", "games": [{"slot": "P1", "side": "top", "team_id": "..."}...]},
             {"name": "Quarterfinals", ...},
             ...
          ],
          "target_path": [...]   # if target_team_id supplied
        }

    Slots whose participants aren't yet determined (e.g. quarterfinal slot
    waiting on a prequarter game) are returned with `source_game` instead
    of `team_id`.
    """
    bdef = load_bracket_definition(bracket_id)

    def resolve_seed(seed_code: str) -> Optional[str]:
        """Resolve a pool-finish code like 'A1', 'B3' -> team id."""
        pool = seed_code[0]
        place_idx = int(seed_code[1:]) - 1
        order = pool_standings.get(pool, [])
        if place_idx < len(order):
            return order[place_idx]
        return None

    rounds_out = []
    # Map game-id -> projected winner team_id (we project chalk: higher pool
    # finish advances; this is a projection, not a simulation).
    projected_winner: dict[str, Optional[str]] = {}

    for rnd in bdef["rounds"]:
        round_games = []
        for game in rnd["games"]:
            participants = []
            for side in ("home", "away"):
                ref = game[side]
                if ref.startswith("W:"):
                    # winner of another game
                    prev = ref[2:]
                    tid = projected_winner.get(prev)
                    participants.append({
                        "side": side,
                        "team_id": tid,
                        "source": f"Winner of {prev}",
                    })
                else:
                    tid = resolve_seed(ref)
                    participants.append({
                        "side": side,
                        "team_id": tid,
                        "source": f"Pool {ref[0]} #{ref[1:]}",
                    })
            # Project the winner: in pure deterministic mode we mark the
            # winner as the participant with the better tournament seed.
            # The actual UI should disclose this is a projection.
            projected_winner[game["id"]] = _project_higher_seed(participants)
            round_games.append({
                "id": game["id"],
                "round": rnd["name"],
                "participants": participants,
                "projected_winner": projected_winner[game["id"]],
            })
        rounds_out.append({"name": rnd["name"], "games": round_games})

    out = {"bracket_id": bracket_id, "rounds": rounds_out}
    if target_team_id is not None:
        out["target_path"] = _trace_target_path(rounds_out, target_team_id)
    return out


def _project_higher_seed(participants: list[dict]) -> Optional[str]:
    """Pick the participant most likely to advance.

    'Better' is decided purely by the source string: A1 > A2 > A3, A1 > B2,
    etc., using overall seed order if we have it (loaded lazily by the API
    layer when seed info is available). For the engine layer we fall back to
    just returning the first non-null team_id -- the UI labels these clearly
    as projections.
    """
    for p in participants:
        if p["team_id"]:
            return p["team_id"]
    return None


def _trace_target_path(rounds: list[dict], target_team_id: str) -> list[dict]:
    """Walk the bracket and surface every game the target team is projected into."""
    path = []
    for rnd in rounds:
        for g in rnd["games"]:
            team_ids = [p["team_id"] for p in g["participants"]]
            if target_team_id in team_ids:
                opponent = next(
                    (p for p in g["participants"] if p["team_id"] != target_team_id),
                    None,
                )
                path.append({
                    "round": rnd["name"],
                    "game_id": g["id"],
                    "opponent_team_id": opponent["team_id"] if opponent else None,
                    "opponent_source": opponent["source"] if opponent else None,
                })
    return path
