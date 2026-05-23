"""
USAU schedule scraper.

play.usaultimate.org is SERVER-rendered (not JS-rendered, despite first
appearances): the HTML source contains the full schedule and pool standings.
So we use plain httpx + BeautifulSoup, which means this works on Render's
standard Python runtime with no Chromium install.

DOM shape (verified live against the 2026 D-I Men's page):

  <h3 class="col_title">Pool A</h3>
  <div class="pool">
    <table class="global_table">         <-- standings
      <tr><th>Team</th><th>W - L</th><th>Tie</th></tr>
      <tr><td>Oregon (1)</td><td>2 - 0</td><td></td></tr>
      ...
    </table>
  </div>
  ...
  <table class="global_table scores_table">   <-- schedule + scores
    <tr><th>Pool A Schedule & Scores</th></tr>
    <tr><th>Date</th><th>Time</th><th>Field</th><th>Team 1</th>
        <th>Team 2</th><th>Score</th><th>Status</th><th>Options</th></tr>
    <tr><td>Fri 5/22</td><td>8:30 AM</td><td>202</td>
        <td>Oregon (1)</td><td>Utah (17)</td>
        <td>15  -  11</td><td>Final</td>...</tr>
    ...
  </table>

Team display text embeds the overall seed in parens: "Oregon (1)". The Tie
column is USAU's pre-computed tiebreaker data ("1-0,5" = head-to-head 1-0,
PD +5); we capture it as a sanity-check signal against our own engine
output.

Live games:
  * Status text is typically "In Progress" while the game is running.
  * Score reflects the LIVE running tally (USAU updates as scorekeepers
    post points). We preserve those running scores -- they're the input
    to the live margin engine.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import Game, Team

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_TEAM_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<seed>\d+)\)\s*$")
_SCORE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def fetch_html(url: str, *, timeout: float = 20.0) -> str:
    """Plain HTTP GET. No Playwright, no JS execution required."""
    r = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=timeout,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.text


def parse_schedule_html(html: str, teams_by_name: dict[str, Team]) -> tuple[list[Game], dict[str, dict]]:
    """
    Returns:
      - list[Game]: all parsed games (final, in_progress, scheduled)
      - dict[pool -> {team_id -> tiecol_text}]: USAU's own pre-computed
        tiebreaker hints from the standings table. Useful for sanity-checking
        our engine output.
    """
    soup = BeautifulSoup(html, "html.parser")
    games: list[Game] = []
    usau_tie_hints: dict[str, dict[str, str]] = {}

    # ---- Schedule tables (one per pool) ---- #
    for tbl in soup.find_all("table", class_="scores_table"):
        pool = _extract_pool_from_header(tbl)
        if not pool:
            continue
        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 7:
                continue
            game = _parse_schedule_row(pool, tds, teams_by_name, line_id=len(games) + 1)
            if game:
                games.append(game)

    # ---- Standings tables (USAU's tiebreaker hints) ---- #
    for h3 in soup.find_all("h3", class_="col_title"):
        m = re.match(r"Pool\s+([A-D])", h3.get_text(strip=True))
        if not m:
            continue
        pool = m.group(1)
        # The standings table is the next <table class="global_table"> (without scores_table)
        tbl = h3.find_next("table", class_="global_table")
        if not tbl or "scores_table" in (tbl.get("class") or []):
            continue
        pool_hints: dict[str, str] = {}
        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            team_text = tds[0].get_text(strip=True)
            tm = _TEAM_RE.match(team_text)
            if not tm:
                continue
            t = teams_by_name.get(tm.group("name").strip())
            if not t:
                continue
            tie = tds[2].get_text(strip=True) if len(tds) >= 3 else ""
            pool_hints[t.id] = tie
        usau_tie_hints[pool] = pool_hints

    return games, usau_tie_hints


def _extract_pool_from_header(tbl: Tag) -> Optional[str]:
    """The first <th> of a schedule table reads 'Pool X Schedule & Scores'."""
    first_th = tbl.find("th")
    if not first_th:
        return None
    m = re.match(r"Pool\s+([A-D])", first_th.get_text(strip=True))
    return m.group(1) if m else None


def _parse_schedule_row(
    pool: str, tds: list[Tag], teams_by_name: dict[str, Team], *, line_id: int
) -> Optional[Game]:
    date = tds[0].get_text(strip=True)
    time = tds[1].get_text(strip=True)
    field = tds[2].get_text(strip=True)
    t1_text = tds[3].get_text(strip=True)
    t2_text = tds[4].get_text(strip=True)
    score = tds[5].get_text(strip=True)
    status_raw = tds[6].get_text(strip=True).lower()

    t1_m = _TEAM_RE.match(t1_text)
    t2_m = _TEAM_RE.match(t2_text)
    if not (t1_m and t2_m):
        return None
    t1 = teams_by_name.get(t1_m.group("name").strip())
    t2 = teams_by_name.get(t2_m.group("name").strip())
    if not (t1 and t2):
        log.warning("unknown team(s): %s / %s", t1_text, t2_text)
        return None

    score_m = _SCORE_RE.match(score)
    if not score_m:
        return None
    s1, s2 = int(score_m.group(1)), int(score_m.group(2))

    if "final" in status_raw:
        status = "final"
        score1, score2 = s1, s2
    elif "progress" in status_raw or "in progress" in status_raw:
        # Live game: preserve the running score
        status = "in_progress"
        score1, score2 = s1, s2
    else:
        status = "scheduled"
        # When USAU shows 0 - 0 with status "Scheduled" the game hasn't started
        if s1 == 0 and s2 == 0:
            score1, score2 = None, None
        else:
            score1, score2 = s1, s2

    return Game(
        game_id=f"{pool}-{line_id:02d}",
        pool=pool,
        team1=t1.id,
        team2=t2.id,
        score1=score1,
        score2=score2,
        status=status,
        scheduled_at=f"{date} {time}",
        field=field,
    )
