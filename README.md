# Ultimate Tracker — 2026 USAU D-I Men's

A live, mobile-first dashboard for the 2026 USAU D-I College Men's
Championships. Pulls scores from `play.usaultimate.org` every 5 minutes
during game hours, applies the official USAU pool-play tiebreaker rules
deterministically, enumerates remaining scenarios, computes **live
in-game margin requirements** as games are happening, and projects the
official 20-team bracket.

**Deployment shape:**

  - **Render cron job** scrapes USAU + pushes JSON to GitHub every 5 min
    (08:30–20:00 America/Chicago, Sat/Sun by default).
  - **GitHub Pages** serves the Next.js static frontend, reading the JSON
    files the cron pushed to the same repo. No always-on backend, no
    Docker, no Chromium.

---

## Table of contents

1. [Architecture](#architecture)
2. [Folder structure](#folder-structure)
3. [Tiebreaker algorithm](#tiebreaker-algorithm)
4. [Live in-game margin engine](#live-in-game-margin-engine)
5. [Scraping plan](#scraping-plan)
6. [Deployment walkthrough](#deployment-walkthrough)
7. [Local development](#local-development)
8. [Testing](#testing)
9. [Extending to other tournaments](#extending-to-other-tournaments)

## Architecture

```
                  +-------------------------+
                  | play.usaultimate.org    |   server-rendered HTML
                  +-----------+-------------+
                              |  httpx GET (no JS, no Chromium)
                              v
+--- Render cron (every 5 min, Sat/Sun 08:30–20:00 CT) ------------+
|  scripts/update_snapshots.py                                     |
|     1. in_run_window() gate                                      |
|     2. scraper.fetch_html + parse_schedule_html                  |
|     3. engine.compute_pool_standing (include_in_progress=True)   |
|     4. engine.enumerate_pool_scenarios                           |
|     5. engine.compute_live_implications      <-- live margins    |
|     6. engine.project_bracket                                    |
|     7. scripts.github_push.push_files -> data/*.json on GitHub   |
+-----------------------------+------------------------------------+
                              |
                              v   git push (Contents API)
                      +---------------+
                      |  GitHub repo  |  data/current.json
                      |     main      |  data/scenarios.json
                      +-------+-------+  data/live.json
                              |          data/bracket.json
                              v
+--- GitHub Actions (.github/workflows/pages.yml) -----------------+
|  on: push to main                                                |
|     1. npm ci + next build (static export)                       |
|     2. copy data/*.json into out/data/                           |
|     3. actions/deploy-pages                                      |
+-----------------------------+------------------------------------+
                              |
                              v
                      GitHub Pages site
                  (loads JSON via relative path)
```

Three layers, each independently testable:

- **Engine** has no I/O. Pure functions over `Game` / `Team` / `Pool`
  dataclasses. Runs the canonical USAU tiebreaker examples as tests with
  no third-party dependencies (`python3 verify_engine.py`).
- **Scraper** turns server-rendered HTML into `List[Game]`. The parser is
  a pure function; only `fetch_html` touches the network.
- **Frontend** reads four static JSON files. Never talks to USAU.

## Folder structure

```
ultimate-tracker/
├── README.md
├── render.yaml                       # Render cron blueprint
├── .github/workflows/pages.yml       # GitHub Pages deploy
├── data/                             # JSONs pushed here by Render cron
│   ├── current.json
│   ├── scenarios.json
│   ├── live.json
│   └── bracket.json
├── backend/
│   ├── build.sh                      # Render build hook
│   ├── requirements.txt              # httpx + bs4 + apscheduler/fastapi (dev)
│   ├── pyproject.toml                # pytest config
│   ├── verify_engine.py              # zero-deps engine test runner
│   ├── scripts/
│   │   ├── update_snapshots.py       # Render cron entry point
│   │   └── github_push.py            # Contents API helper
│   └── app/
│       ├── main.py                   # OPTIONAL local FastAPI (dev only)
│       ├── config.py
│       ├── store.py
│       ├── models.py                 # dataclasses
│       ├── scraper/
│       │   └── usau.py               # httpx + BeautifulSoup
│       ├── engine/
│       │   ├── tiebreaker.py         # *** USAU rules engine ***
│       │   ├── standings.py          # supports include_in_progress
│       │   ├── scenarios.py          # only enumerates SCHEDULED games
│       │   ├── live.py               # *** in-game margin engine ***
│       │   └── bracket.py
│       └── data/
│           ├── tournament_2026_mens.json
│           └── bracket_17_4.json
└── frontend/
    ├── package.json
    ├── next.config.js                # output: "export" (static site)
    ├── tailwind.config.js
    └── app/
        ├── layout.tsx
        ├── page.tsx                  # tab nav + data fetch
        ├── globals.css
        ├── lib/{api.ts, types.ts}
        └── tabs/
            ├── PoolDashboard.tsx
            ├── LiveMargins.tsx       # *** the live in-game tab ***
            ├── ScenarioMatrix.tsx
            ├── ProjectedBracket.tsx
            └── TexasPath.tsx
```

## Tiebreaker algorithm

`backend/app/engine/tiebreaker.py` implements the official USAU
round-robin tiebreaker rules from pages 6-7 of the UPA Manual of
Championship Series Tournament Formats. Rules 1, 1a, 1b, 2, 3, 4 today;
Rules 5–10 scaffolded as `NotImplementedError`.

```
def order_teams(tied, games, start_rule=2):
    rule = start_rule
    while rule <= MAX_RULE:
        metric_per_team = compute(rule, tied, games)
        groups = group_by_metric_descending(metric_per_team)
        if len(groups) == 1:
            rule += 1                                  # Rule 1a
            continue
        # Rule 1b: subgroups -> recurse, restarting at Rule 2.
        return flatten(g if len(g)==1 else order_teams(g, games, 2)
                       for g in groups)
```

The non-obvious bit is Rule 1b's restart semantics: when a rule splits a
three-way tie into `{A}` and `{B,C}`, the remaining `{B,C}` re-enters at
**Rule 2** (head-to-head), not at Rule 4 where we just were. The unit
tests pin this down explicitly with Example 3.2 from the manual.

Engine output includes a `TieBreakTrace` per decision so the UI can show
exactly which rule resolved each tie — great for the sideline question
"why is Texas 2nd, not 3rd?".

## Live in-game margin engine

`backend/app/engine/live.py` is the answer to **"Texas is up 10-8 on UCSC
right now. How many more points do they need to clinch 2nd?"**

For each in-progress game involving the target team, the engine:

1. Identifies the **other unfinished pool games**:
   - other in-progress games -> frozen at their current running scores
   - scheduled games -> enumerated 2^N over W/L outcomes
2. Sweeps the target's possible final margin from `-14` to `+14`.
3. For every `(combo, margin)` cell, synthesizes the final pool game set
   and computes the standings.
4. Records the target's resulting finish position.
5. Derives per-finish thresholds: "minimum margin to achieve finish X" +
   "margin at which finish X is GUARANTEED regardless of other games".

The frontend's **Live tab** renders this as cards: each in-progress
target game shows running score, plus per-finish guidance like:

> **Finish #2** — Guaranteed at final margin ≥ +3 · need to extend lead by +1 from here

The "matrix" payload is also exposed so users can drill into each combo.

This is purely deterministic. No probability, no Monte Carlo.

## Scraping plan

USAU's `play.usaultimate.org/events/2026-D-I-College-Championships/
schedule/Men/CollegeMen/` is **server-rendered HTML**. I verified that
plain `httpx.get` with a real browser User-Agent returns the full
schedule -- no headless browser required.

The DOM shape (verified against live data):

- Pool standings: `<h3 class="col_title">Pool A</h3>` followed by
  `<table class="global_table">`. Columns: Team | W - L | Tie.
  The "Tie" column shows USAU's own pre-computed tiebreaker hints
  (e.g. `1-0,5` = head-to-head 1-0, point diff +5) -- we capture them
  for sanity-checking our engine output.
- Pool schedule: `<table class="global_table scores_table">`. Columns:
  Date | Time | Field | Team 1 | Team 2 | Score | Status | Options.
  Team text format: `"Oregon (1)"`. Score format: `"15  -  11"`.
  Status: "Final" / "Scheduled" / "In Progress".

`parse_schedule_html` (in `backend/app/scraper/usau.py`) preserves
in-progress games with their running scores, which is the input to the
live margin engine.

## Deployment walkthrough

### 1. Push to GitHub

Create a new GitHub repo and push this directory:

```bash
cd ultimate-tracker
git init
git branch -M main
git add .
git commit -m "Initial commit"
git remote add origin git@github.com:YOUR-USER/ultimate-tracker.git
git push -u origin main
```

### 2. Set up the GitHub Personal Access Token (for the cron to push back)

GitHub -> Settings -> Developer settings -> Personal access tokens ->
Fine-grained tokens. Generate one with:

- Repository access: only-selected -> your ultimate-tracker repo
- Permissions: **Repository contents: Read and write**

Copy the token (you'll paste it into Render in a moment).

### 3. Create the Render cron job

Option A -- Blueprint (auto-detect from `render.yaml`):

1. Render Dashboard -> "New +" -> "Blueprint"
2. Connect your GitHub repo
3. Render reads `render.yaml`, creates the cron service named
   `usau-snapshot-cron`
4. In the new service's "Environment" tab, set:
   - `GITHUB_TOKEN` = the PAT from step 2
   - `GITHUB_REPO` = `YOUR-USER/ultimate-tracker`

Option B -- Manual:

1. Render Dashboard -> "New +" -> "Cron Job"
2. Connect repo, set Root Directory: `backend`
3. Build Command: `./build.sh`
4. Start Command: `python -m scripts.update_snapshots`
5. Schedule: `*/5 * * * *` (every 5 min; window check in script enforces game hours)
6. Add the env vars as in Option A above

The cron's `in_run_window` gate (see `update_snapshots.py`) defaults to
**Sat/Sun, 08:30–20:00 America/Chicago**. To extend, override env vars
in Render's dashboard (no code change needed):

- `RUN_WINDOW_DAYS=Sat,Sun,Mon`
- `RUN_WINDOW_START=08:00`
- `RUN_WINDOW_END=21:30`
- `RUN_WINDOW_TZ=America/Chicago`
- `ALLOW_ANY_TIME=1` (for manual trigger from the Render dashboard)

### 4. Enable GitHub Pages

In your repo settings:

1. Settings -> Pages -> Source: "GitHub Actions"
2. Push to `main` -> the `.github/workflows/pages.yml` workflow runs
3. After the first run, your site is live at
   `https://YOUR-USER.github.io/ultimate-tracker/`

Every subsequent push (including the cron-job commits) triggers a fresh
deployment. Concurrency settings in the workflow prevent stacked builds.

### 5. First-run sanity check

In the Render dashboard, open the cron service and click "Run now". Add
the env var `ALLOW_ANY_TIME=1` temporarily so the run-window gate is
bypassed. You should see logs like:

```
in window: ALLOW_ANY_TIME=1
loaded tournament: 2026 D-I College Championships (target=texas)
parsed 40 games (5 final, 0 in-progress, 35 scheduled)
data/current.json: created
data/scenarios.json: created
data/live.json: created
data/bracket.json: created
pushed 4 files to YOUR-USER/ultimate-tracker
```

A new commit will appear on `main`, the Pages workflow will run, and a
few minutes later your dashboard is live.

## Local development

Backend (Python 3.11+):

```bash
cd backend
pip install -r requirements.txt        # httpx + bs4 + (optional) fastapi
python3 verify_engine.py               # zero-deps smoke test
DRY_RUN=1 ALLOW_ANY_TIME=1 python -m scripts.update_snapshots
# -> writes JSONs to ../data/ for local frontend dev
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev
# -> http://localhost:3000  (reads ../data/*.json via Next.js)
```

## Testing

The engine layer has 20 zero-dependency tests:

```bash
cd backend
python3 verify_engine.py
```

Coverage:

- 6 canonical USAU tiebreaker examples (2.1, 2.2, 2.3/3.1, 3.2, 3.3/4.1, 4.2)
- Pool A end-of-Day-1 standings against live USAU data
- Scenario enumerator (2^N permutations, in-progress freezing)
- Live margin engine (running-score capture, summary, matrix)
- Bracket projector (pool winners -> QF, 17.4 structure)
- `include_in_progress` flag on standings

The Example 3.2 test is the safety-critical one: it exercises the Rule
1b subgroup recursion that is by far the easiest USAU rule to implement
incorrectly.

## Extending to other tournaments

1. Add `backend/app/data/tournament_<id>.json` with teams + pools + target.
2. Add `backend/app/data/bracket_<id>.json` if bracket shape differs from 17.4.
3. Set env var `TOURNAMENT_FILE=app/data/tournament_<id>.json`.
4. Push; cron picks it up on next tick.

No code changes required. The tiebreaker, scenario, live-margin, and
bracket engines are all tournament-agnostic.
