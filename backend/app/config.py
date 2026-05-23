"""
Configuration. Single source of truth for paths and scheduler interval.
Everything tournament-specific is read from JSON in app/data/.
"""
from __future__ import annotations

import os
from pathlib import Path

# Backend root: backend/app/  -> project root: backend/
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"

# Where the scraper writes its JSON snapshots. Mapped to a docker volume so the
# frontend can serve them as static files.
OUT_DIR = Path(os.environ.get("OUT_DIR", "/data"))

# How often the scraper runs (seconds). 5 minutes by default per the spec.
SCRAPE_INTERVAL_SECONDS = int(os.environ.get("SCRAPE_INTERVAL_SECONDS", "300"))

# Which tournament definition to load. Add more files in data/ to support
# additional tournaments / divisions.
TOURNAMENT_FILE = os.environ.get(
    "TOURNAMENT_FILE",
    str(DATA_DIR / "tournament_2026_mens.json"),
)

# Whether to log Playwright traffic
DEBUG_SCRAPER = os.environ.get("DEBUG_SCRAPER", "0") == "1"
