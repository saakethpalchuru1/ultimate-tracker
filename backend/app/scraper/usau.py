"""USAU schedule scraper.

play.usaultimate.org is server-rendered: a plain httpx GET with a real
browser User-Agent returns the full schedule HTML, no JS needed.

DOM shape (verified live):

  <h3 class="col_title">Pool A</h3>
  <table class="global_table">         <-- standings (separate from schedule)
    <tr><th>Team</th><th>W - L</th><th>Tie</th></tr>
    ...
  </table>
  <table class="global_table scores_table">   <-- pool play schedule + scores
    <tr><th>Pool A Schedule & Scores</th></tr>
    <tr><th>Date</th>...<th>Score</th><th>Status</th>...</tr>
    <tr><td>Fri 5/22</td>...<td>15  -  11</td><td>Final</td>...</tr>
    ...
  </table>

DEFENSIVE STATUS DETECTION:
USAU has been known to leave a row's status as "Scheduled" while the
scoreboard is actively updating. We therefore treat any non-Final row
with a non-zero score as in_progress, regardless of what USAU's status
column says. Specifically:
  status == "Final"          -> final
  "in progress" in status    -> in_progress
  score is non-zero          -> in_progress  (USAU's label is stale)
  otherwise                  -> scheduled    (genuinely not started)
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
    r = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=timeout,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.text


def parse_schedule_html(html: str, teams_by_name: dict[str, Team]) -> tuple[list[Game], dict[str, dict]]:
    soup = BeautifulSoup(html, "html.parser")
    games: list[Game] = []
    usau_tie_hints: dict[str, dict[str, str]] = {}

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

    for h3 in soup.find_all("h3", class_="col_title"):
        m = re.match(r"Pool\s+([A-D])", h3.get_text(strip=True))
        if not m:
            continue
        pool = m.group(1)
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

    # DEFENSIVE: USAU sometimes leaves status="Scheduled" while scores
    # are actively updating. Treat any non-Final row with a non-zero
    # score as in_progress, regardless of USAU's status text.
    if "final" in status_raw:
        status = "final"
        score1, score2 = s1, s2
    elif "in progress" in status_raw or "progress" in status_raw or (s1 + s2) > 0:
        status = "in_progress"
        score1, score2 = s1, s2
    else:
        status = "scheduled"
        score1, score2 = None, None

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
