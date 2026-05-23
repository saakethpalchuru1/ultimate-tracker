"""
USAU pool-play tiebreaker engine.

Implements the official USA Ultimate round-robin tiebreaker rules:

  Rule 1   - A given tiebreaker rule applies equally to ALL the tied teams.
  Rule 1a  - If, after applying a rule, all teams are still tied, advance to
             the next rule.
  Rule 1b  - If a rule splits the tied set into 2+ subgroups, separate them
             and recurse back to RULE 2 for each subgroup (NOT continue from
             the rule that produced the split).
  Rule 2   - Won-loss record counting only games among the tied teams.
  Rule 3   - Point differential counting only games among the tied teams.
  Rule 4   - Point differential vs all common opponents (opponents that
             *every* tied team has played).
  Rule 4a  - When a team has played a common opponent multiple times,
             average those games.
  Rules 5-10 are scaffolded but not yet implemented (user requested 1-4 only).

The engine is deterministic and side-effect-free. It returns BOTH the
final ordered list of teams AND a trace explaining how each tie was broken,
which is what the UI consumes to render the standings explanations.

Reference: pages 6-7 of "The UPA Manual of Championship Series Tournament
Formats" (USAU). Examples 2.1 .. 4.2 from the manual are reproduced as
unit tests in tests/test_tiebreaker.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..models import Game


# How many rules we currently implement. Bump as Rules 5+ are added.
MAX_RULE = 4


@dataclass(frozen=True)
class TieBreakTrace:
    """One trace entry per tiebreaker decision the engine made."""
    rule: int                       # which rule resolved this
    tied_team_ids: tuple[str, ...]  # the set of teams entering this resolution
    metric_values: dict[str, float] # team_id -> numeric metric used
    outcome: str                    # 'split' | 'all_still_tied' | 'single_team'
    note: str = ""


def order_teams(
    tied_team_ids: list[str],
    games: list[Game],
    start_rule: int = 2,
    trace: Optional[list[TieBreakTrace]] = None,
) -> list[str]:
    """
    Order a set of tied teams using USAU tiebreaker rules.

    `tied_team_ids` MUST all share the same W-L record (the caller is
    responsible for grouping by record first; this function only resolves
    *within* a single W-L tier).

    `games` is the full set of pool games (final games only are used).
    Games involving teams outside the tied set are still passed in because
    Rule 4 needs common-opponent data.

    `start_rule` lets callers re-enter at a specific rule, but per Rule 1b
    the recursive calls always re-enter at Rule 2.

    Returns: ordered list of team_ids, best-to-worst.
    Mutates: appends TieBreakTrace records to `trace` if provided.
    """
    if trace is None:
        trace = []

    teams = list(tied_team_ids)
    if len(teams) <= 1:
        return teams

    rule = start_rule
    while rule <= MAX_RULE:
        metrics = _compute_metric(teams, games, rule)
        groups = _group_by_metric(teams, metrics)

        if len(groups) == 1:
            # Rule 1a: rule failed to split anybody. Advance.
            trace.append(TieBreakTrace(
                rule=rule,
                tied_team_ids=tuple(sorted(teams)),
                metric_values={t: metrics[t] for t in teams},
                outcome="all_still_tied",
            ))
            rule += 1
            continue

        # Rule 1b: at least one split happened. Recurse on each subgroup,
        # restarting at Rule 2 per the official rule.
        trace.append(TieBreakTrace(
            rule=rule,
            tied_team_ids=tuple(sorted(teams)),
            metric_values={t: metrics[t] for t in teams},
            outcome="split",
            note=f"split into {len(groups)} subgroup(s)",
        ))
        ordered: list[str] = []
        for subgroup in groups:
            if len(subgroup) == 1:
                ordered.extend(subgroup)
            else:
                ordered.extend(order_teams(subgroup, games, start_rule=2, trace=trace))
        return ordered

    # Exhausted all implemented rules; fall back to seed order (stable
    # deterministic placeholder until Rules 5-10 are added).
    teams_sorted = sorted(teams)  # deterministic; in production seed order
    trace.append(TieBreakTrace(
        rule=MAX_RULE,
        tied_team_ids=tuple(sorted(teams)),
        metric_values={},
        outcome="all_still_tied",
        note="exhausted implemented rules; fell back to deterministic order",
    ))
    return teams_sorted


# ----------------------------- metrics ----------------------------- #

def _compute_metric(teams: list[str], games: list[Game], rule: int) -> dict[str, float]:
    """Returns metric value per team; HIGHER is better."""
    if rule == 2:
        return _rule2_wl_among_tied(teams, games)
    if rule == 3:
        return _rule3_pd_among_tied(teams, games)
    if rule == 4:
        return _rule4_pd_common_opponents(teams, games)
    raise NotImplementedError(f"Rule {rule} not implemented")


def _rule2_wl_among_tied(teams: list[str], games: list[Game]) -> dict[str, float]:
    """Wins counting only games among the tied teams."""
    s = set(teams)
    wins = {t: 0 for t in teams}
    for g in games:
        if not g.is_final:
            continue
        if g.team1 in s and g.team2 in s:
            w = g.winner
            if w in wins:
                wins[w] += 1
    return {t: float(wins[t]) for t in teams}


def _rule3_pd_among_tied(teams: list[str], games: list[Game]) -> dict[str, float]:
    """Point differential counting only games among the tied teams."""
    s = set(teams)
    pd = {t: 0 for t in teams}
    for g in games:
        if not g.is_final:
            continue
        if g.team1 in s and g.team2 in s:
            pd[g.team1] += (g.score1 - g.score2)
            pd[g.team2] += (g.score2 - g.score1)
    return {t: float(pd[t]) for t in teams}


def _rule4_pd_common_opponents(teams: list[str], games: list[Game]) -> dict[str, float]:
    """
    Point differential counting games against COMMON opponents -- opponents
    outside the tied set that EVERY tied team has played at least once.

    Rule 4a: when a tied team has played the same common opponent multiple
    times, average the differentials.
    """
    tied_set = set(teams)

    # For each tied team, build {opponent_id -> list of point differentials}
    diffs: dict[str, dict[str, list[int]]] = {t: {} for t in teams}
    for g in games:
        if not g.is_final:
            continue
        if g.team1 in tied_set and g.team2 not in tied_set:
            diffs[g.team1].setdefault(g.team2, []).append(g.score1 - g.score2)
        elif g.team2 in tied_set and g.team1 not in tied_set:
            diffs[g.team2].setdefault(g.team1, []).append(g.score2 - g.score1)
        # games between tied teams are explicitly excluded

    # Common opponents = intersection of opponent sets across all tied teams
    opp_sets = [set(diffs[t].keys()) for t in teams]
    common = set.intersection(*opp_sets) if opp_sets else set()

    if not common:
        # No common opponents -> rule yields equal metric for everybody;
        # the caller will advance to the next rule per 1a.
        return {t: 0.0 for t in teams}

    result: dict[str, float] = {}
    for t in teams:
        total = 0.0
        for opp in common:
            d = diffs[t][opp]
            total += sum(d) / len(d)   # average per opponent (Rule 4a)
        result[t] = total
    return result


# ----------------------------- grouping ----------------------------- #

def _group_by_metric(teams: list[str], metrics: dict[str, float]) -> list[list[str]]:
    """
    Group teams by metric value, returning groups ordered best-to-worst.
    Teams with equal metric stay together (those subgroups will be recursed on).
    """
    # Sort by metric DESCENDING (higher is better), break sort-ties by team id
    # for determinism (the recursion will then further break those ties).
    sorted_teams = sorted(teams, key=lambda t: (-metrics[t], t))
    groups: list[list[str]] = []
    current: list[str] = []
    current_val: Optional[float] = None
    for t in sorted_teams:
        v = metrics[t]
        if current_val is None or v == current_val:
            current.append(t)
            current_val = v
        else:
            groups.append(current)
            current = [t]
            current_val = v
    if current:
        groups.append(current)
    return groups
