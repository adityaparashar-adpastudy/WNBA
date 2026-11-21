WNBA Court Intelligence
=======================
A local WNBA adaptation of the supplied NBA Python/Flask dashboard and
ESPN WNBA season scrapers. Original files in Downloads/NBA were preserved.

RUN ON MAC
Keep this entire folder at ~/Downloads/WNBA.
From Terminal you can also start it with:
  cd ~/Downloads/WNBA
  bash start.command

Double-click start.command. On first launch it creates a local .venv and
installs Flask and requests from PyPI. Open http://127.0.0.1:5050.
Keep the Terminal window open; press Control-C to stop.

OR RUN FROM TERMINAL
cd into this WNBA folder, then:
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -r requirements.txt
  python app.py

FEATURES
- Overview with four core metrics, participation chart and utilization ring.
- Teams discovered from ESPN, plus historical 2025 teams for past-season queries.
- Single-year seasons, regular season/playoff selection, first 5/10/20 or all games.
- Game search, per-game player details and source links.
- CSV export of games matching the current text search.
- Background queries with progress, partial-failure reporting and response caching.
- No API key required. Internet needed for uncached data.

DATA AND DEFINITIONS
The initial snapshot is real ESPN data: first 10 Indiana Fever regular-season
games from 2025. It is a sample, not full-season or live data.
Refresh source bypasses the local response cache. Query results appear in the
browser; the CLI below saves a new startup snapshot.

Box-score listed: unique players in that game's team player block. Does not
prove dressed availability, and is not the total season roster.
Entered: numeric minutes and no didNotPlay flag, including rounded zero minutes.
Injury DNP: a non-participant with an explicit injury/illness keyword in the
source reason. This is a text heuristic. Unspecified reasons are unclassified.
DNP is NOT automatically an injury. In-game injuries remain unknown.
Minutes are summed player-minutes: 200 regulation, plus 25 per overtime.
ESPN rounds player minutes, so observed totals may differ. Overtime uses the
source period, never the noisy summed minutes.
Commissioner's Cup championship excluded; qualifying games retained.
Failed games are excluded from averages; coverage and errors remain visible.
The undocumented ESPN endpoint may change or be rate-limited. No guarantee of
complete injury reasons. See Methodology in the dashboard for details.
Current teams can be selected with historical seasons in which they did not
exist; those queries return no games rather than fabricated data.

SAVE A DIFFERENT STARTUP SNAPSHOT
  python collector.py --team ind --season 2025 --limit 0 --output data/snapshot.json
  python collector.py --team sea --season 2025 --limit 5 --postseason --output data/snapshot.json
--limit 0 means all completed games. Use ESPN IDs or team abbreviations.

CHECKS
  python -m unittest discover -s tests -v
  node --check static/app.js
Seven tests cover minute parsing, DNP evidence, duplicate player groups, missing
team blocks, Cup exclusion, failed-game coverage and API input validation.
Live ESPN collection and browser query/player/search flows also verified.

FILES
app.py              Flask JSON API and background query jobs
collector.py        WNBA ESPN collector + CLI (replaces subprocess log parsing)
templates/index.html Dashboard views
static/             Responsive CSS and plain JavaScript (no frontend build)
data/snapshot.json  Real starter dataset
data/cache/         Cached public ESPN responses (remove to clear cache)
tests/              Metric and API regression checks

LOCAL USE
Binds only to 127.0.0.1:5050. No hosting account or public deployment required.

SOURCES
https://www.espn.com/wnba/
https://site.api.espn.com/apis/site/v2/sports/basketball/wnba
https://rulebook.wnba.com/rule-no-5-scoring-and-timing/
