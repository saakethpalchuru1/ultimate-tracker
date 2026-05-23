"""Render cron entry-point. Scrapes USAU, computes snapshots, pushes to GitHub, purges jsdelivr."""
from __future__ import annotations
import logging, os, sys, urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import store
from app.pipeline import build_snapshots_from_games
from app.scraper.usau import fetch_html, parse_schedule_html
from scripts.github_push import push_files

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("update_snapshots")

USAU_URL = ("https://play.usaultimate.org/events/2026-D-I-College-Championships/"
            "schedule/Men/CollegeMen/?ViewAll=true&bracket=true")


def in_run_window():
    if os.environ.get("ALLOW_ANY_TIME") == "1":
        return True, "ALLOW_ANY_TIME=1"
    tz = ZoneInfo(os.environ.get("RUN_WINDOW_TZ", "America/Chicago"))
    now = datetime.now(tz)
    days_env = os.environ.get("RUN_WINDOW_DAYS", "Sat,Sun")
    allowed_days = {d.strip().lower()[:3] for d in days_env.split(",")}
    if now.strftime("%a").lower()[:3] not in allowed_days:
        return False, "day " + now.strftime("%a") + " not in allowed " + str(sorted(allowed_days))
    start_h, start_m = (int(x) for x in os.environ.get("RUN_WINDOW_START", "08:30").split(":"))
    end_h, end_m = (int(x) for x in os.environ.get("RUN_WINDOW_END", "20:00").split(":"))
    start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if not (start <= now <= end):
        return False, "local time " + now.strftime("%H:%M") + " outside window"
    return True, "in window (" + now.isoformat() + ")"


def purge_jsdelivr():
    repo = os.environ.get("GITHUB_REPO", "saakethpalchuru1/ultimate-tracker")
    for name in ("current.json", "scenarios.json", "bracket.json", "live.json"):
        url = "https://purge.jsdelivr.net/gh/" + repo + "@main/data/" + name
        try:
            urllib.request.urlopen(url, timeout=5).read()
        except Exception as e:
            log.warning("jsdelivr purge %s failed: %s", name, e)


def main():
    ok, reason = in_run_window()
    if not ok:
        log.info("skipping: %s", reason)
        return 0
    log.info("in window: %s", reason)

    tournament = store.load_tournament()
    try:
        html = fetch_html(USAU_URL)
        teams_by_name = {t.name: t for t in tournament.teams}
        games, usau_tie_hints = parse_schedule_html(html, teams_by_name)
        log.info("parsed %d games", len(games))
    except Exception:
        log.exception("scrape failed"); return 1
    try:
        files = build_snapshots_from_games(tournament, games, usau_tie_hints)
    except Exception:
        log.exception("snapshot build failed"); return 1

    if os.environ.get("DRY_RUN") == "1" or not os.environ.get("GITHUB_TOKEN"):
        out_dir = Path(__file__).resolve().parent.parent.parent / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        for relpath, content in files.items():
            (out_dir / Path(relpath).name).write_text(content, encoding="utf-8")
        log.info("dry-run: wrote %d files to %s", len(files), out_dir)
        return 0

    push_files(files, commit_message="live update " + store.utcnow_iso())
    log.info("pushed %d files to %s", len(files), os.environ.get("GITHUB_REPO"))
    purge_jsdelivr()
    log.info("jsdelivr purged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
