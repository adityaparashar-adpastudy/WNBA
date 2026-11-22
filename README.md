# WNBA
WNBA Injury Data Repo

Season availability and historical limits (2026-11-22)

The season selector now uses `data/season_coverage.json`. An availability audit checked 930 schedules: 1997–2027 × 15 currently selectable franchise IDs × regular season/playoffs. For each nonempty schedule, the first completed player box score was sampled. This is not an all-games injury audit. Seasons 1997–2002 and 2027 had no usable sampled player data and are hidden; 2013–2026 remain selectable. The catalog does not cover every defunct historical franchise. Adding future years requires verifying source data and refreshing the coverage manifest, so an empty future season is not automatically advertised.

When no official snapshot is loaded, the primary panel shows recorded ESPN DNP reasons and a partial-evidence warning. The injury export then exports only explicitly injury-related nonparticipants, with full names and original reasons. Missing players remain missing, not zero injuries. Atlanta 2025 first20 contains only two ESPN injury-DNP rows; the official May25 gamebook lists injured inactive players omitted from ESPN. Historical injuries have therefore NOT been comprehensively backfilled. Example: https://statsdmz.nba.com/pdfs/20250525/20250525_CONATL.pdf

Latest source comparison

Open “Compare latest source listings” and load ESPN/Action Network. `/api/current-injuries` retrieves their independent source lists with a five-minute cache, dates, attribution, original statuses/details and warnings on rows over seven days old. The official WNBA source remains dated game snapshots; no latest-page snapshot is claimed. Outlet lists may include offseason-stale statuses, disagreements, duplicates and non-injury reasons. They are **not joined to historical games, counted as unique injuries, or treated as primary confirmation**. Failed retrieval is Unavailable. The comparison export includes source provenance, confidence and the requested research fields; unreconciled season, side, actual return date and games missed remain blank. A source body-site label is preserved only when explicit; no diagnosis is inferred.

Evidence hierarchy: team/league statements first; credible outlet reports remain reported pending primary verification; encyclopedia pages are leads only. Official CSV confidence “confirmed” confirms the league report designation, not a diagnosis, incident or actual absence. Box-score and news rows are “reported.” Game-log gaps never establish injury. Games missed and actual return dates require dated injury evidence plus game-by-game reconciliation. Overseas/offseason origin remains unverified unless sourced. Pre-2023 minor injuries and short absences may be substantially under-covered. No complete public injury registry or clinical validation is claimed.

Final selector criterion: usable player data plus an identifiable injury reason in the availability sample. 2003–2012 have some player data but no identifiable injury reasons in these samples, so they are also hidden pending injury verification. Visible seasons: 2013–2026. Sampling does not prove the hidden years have no public injury information, nor that visible years are complete.
