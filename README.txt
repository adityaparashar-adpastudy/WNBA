WNBA Court Intelligence — injury evidence and playing time
==========================================================

Run on Mac:
  cd ~/Downloads/WNBA
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -r requirements.txt
  python app.py
Open http://127.0.0.1:5050. start.command remains an alternative launcher.

Render build: pip install -r requirements.txt
Render start: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
Use one worker: background jobs are held in that process. A restart clears jobs.
The UI polls background jobs, so full-season collection can outlast one browser request.
Two queries run concurrently; retained job results are bounded and expire after one hour.

WHAT THE DATA MEANS
Official WNBA reports are separate from ESPN box-score DNP reasons and actual participation.
wnba_official_reports.py retrieves selected available submitted pregame PDF snapshots from
the official WNBA endpoint. It preserves source player name, team, game date/matchup, report
status, original reason (PDF whitespace normalized), report timestamp and PDF URL. Reports
must match the team and Eastern game date/matchup, precede tipoff and be under 36 hours old.
Unsubmitted, missing, malformed or unmatched reports are unavailable, never zero injuries.
The parser reconciles player and reason rows and fails closed on unsupported layouts.

The first available snapshot from a bounded set of observed pregame filename times is used.
It is not necessarily the final report before tipoff. Later revisions and injuries not in
that snapshot may be absent. Verified integration support is for the 2026 PDF format;
pre-2026 official archive coverage has not been established and is explicitly unavailable.
Selecting an earlier year does not create complete historical injury data. ESPN DNP reasons
for those seasons remain separate partial evidence. No complete public-injury registry,
clinical diagnosis, injury incidence or in-game injury detection is claimed.

Every report status is preserved. An injury-listed player may still play. Totals are
player-game designations, not unique injury episodes or confirmed injury-related absences.
Repeated entries across games are not medically deduplicated. Injury, illness, other and
unknown categories use conservative source wording; the Injury/Illness umbrella heading is
not itself evidence of illness. Missing or mixed causes remain unknown. A collapsed-lung
or reconditioning report does not establish an injury-versus-illness cause.

ESPN may omit inactive injured players. Official report records remain independent of the
box-score list. Exact normalized names link the sources; ambiguous/unmatched players keep
blank IDs and unknown participation/time. An Out designation alone does not prove absence.
If an ESPN box score fails, its completed scheduled game remains with null player metrics;
any available official report remains visible and exportable. Such rows are excluded from
participation charts and statistical averages, and their source errors remain displayed.

Participation is played, absent or unknown. Missing minutes or contradictory DNP/minute
fields do not establish nonparticipation. Participation-unknown records are excluded from
both entered-player and confirmed-DNP totals. Generic DNP, DID NOT DRESS or INACTIVE does not
establish a reason; it is unknown. Recognized non-injury reasons are other, which does not
prove the player was healthy. Original reason wording is retained for review.

Playing time preserves raw ESPN values and marks rounded whole minutes, decimal minutes,
reported seconds, confirmed DNP zero or unavailable. Whole-minute reports are not verified
minute:second exposure. Regulation is 200 team player-minutes plus 25 per overtime, while
summed rounded player minutes may differ. OT comes from period metadata, not rounded sums.
Dates use venue-local IANA timezones with explicitly labeled UTC/source-date fallbacks.

SCOPE AND EXPORTS
Teams use the current ESPN catalog plus historical 2025 teams. Season choices run from
1997 through next year automatically. Regular season and playoffs are separate queries.
Completed games are chronological; the separately flagged Cup championship is excluded.
Source availability varies by team, date and season. Empty future seasons remain empty.

Export games CSV includes the current opponent/date search results and separate game,
box-score and official-report coverage fields. Four player-level downloads use those same
filtered games: official injuries only, all official report records, playing time for all
listed ESPN players, and box-score nonparticipants/participation-unknown records. Official
exports include injured players who played and those missing from ESPN. Team/player full
names, IDs when safely matched, reasons/status, game/season, source links, report time,
playing-time precision and coverage limits accompany the player rows. Missing time is blank,
not zero. Files use UTF-8 BOM, quoted CSV fields and spreadsheet formula protection.

CACHE AND STARTUP SAMPLE
The startup snapshot is a saved first-ten Indiana Fever sample from 2025, not live data or
a complete injury registry. It is schema version 3. Refresh source bypasses ESPN caching.
Schedules expire after five minutes, the team catalog after 24 hours and summaries after
one hour. Official PDF requests use bounded five-minute in-memory caching. WNBA_CACHE_DIR
can redirect ESPN caches. Cache contents are public source responses, not a durable
research database. No API key is required.

Checks:
  python -m unittest discover -s tests -v
  node tests/test_player_export.cjs
  node --check static/app.js

The 2025 retained-source replay covers all 310 unique regular/playoff games (620 team-game
rows, 7,093 player-game rows). It preserves scores, minutes and game coverage while correcting
21 previous false-absence records to participation unknown. This is source-fidelity testing,
not independent clinical validation. Live 2026 regular-season and playoff queries checked all 15 teams: 706 team-game
records with matching submitted official snapshots. Of these, 702 had player box scores;
two ESPN games (four team-game records) returned 404. Official reports for those games
remain available while player participation/minutes stay unavailable. The 2026 audit
retains 8,526 ESPN player-game rows. These are checks of selected snapshots, not every
report revision or every public injury. Detailed audit artifacts accompany this update. Passing software tests cannot guarantee zero source errors.

Sources:
https://www.wnba.com/wnba-injury-report
https://site.api.espn.com/apis/site/v2/sports/basketball/wnba
https://rulebook.wnba.com/rule-no-5-scoring-and-timing/
