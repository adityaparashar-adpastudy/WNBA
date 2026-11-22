"""WNBA data adapter, consolidated from the supplied ESPN season scrapers."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
import json
import os
from pathlib import Path
import re
import time
import math
import requests

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba'
CACHE = Path(os.environ.get('WNBA_CACHE_DIR',Path(__file__).parent / 'data' / 'cache'))
# Offline selector for the historical 2025 season; online catalog is preferred.
TEAMS_2025 = [('20','ATL','Atlanta Dream'),('19','CHI','Chicago Sky'),('18','CONN','Connecticut Sun'),('3','DAL','Dallas Wings'),('129689','GS','Golden State Valkyries'),('5','IND','Indiana Fever'),('17','LV','Las Vegas Aces'),('6','LA','Los Angeles Sparks'),('8','MIN','Minnesota Lynx'),('9','NY','New York Liberty'),('11','PHX','Phoenix Mercury'),('14','SEA','Seattle Storm'),('16','WSH','Washington Mystics')]
# Use abbreviations as route slugs, avoiding source-specific numeric IDs.
FALLBACK = [dict(id=tid, abbreviation=code, displayName=name) for tid,code,name in TEAMS_2025]

def fetch(path, params=None, refresh=False):
    key = hashlib.sha256((path + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
    file = CACHE / (key + '.json')
    # Mutable schedules and team catalogs must not remain cached forever.
    max_age = 300 if path.endswith('/schedule') else 86400 if path == '/teams' else 3600
    fresh = file.exists() and (max_age is None or time.time()-file.stat().st_mtime < max_age)
    if fresh and not refresh:
        return json.loads(file.read_text())
    response = requests.get(BASE + path, params=params, timeout=(10, 30), headers={'User-Agent':'WNBA-Research-Dashboard/1.0'})
    response.raise_for_status()
    data = response.json()
    CACHE.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix(f'.{os.getpid()}.{time.time_ns()}.tmp')
    temp.write_text(json.dumps(data))
    temp.replace(file)
    return data

def teams():
    try:
        data = fetch('/teams')
        catalog = {t['displayName']:t for t in FALLBACK}
        catalog.update({x['team']['displayName']:x['team'] for x in data['sports'][0]['leagues'][0]['teams']})
        return list(catalog.values())
    except (requests.RequestException, KeyError, ValueError):
        return FALLBACK

def minutes(value):
    if value in (None, '', '--', 'DNP'): return None
    try:
        if ':' in str(value):
            if not re.fullmatch(r'\d+:\d{2}',str(value)):return None
            m,s = str(value).split(':')
            result=int(m)+int(s)/60
            return result if int(s)<60 else None
        result=float(value)
        return result if math.isfinite(result) and result>=0 else None
    except (ValueError, TypeError): return None


# Venue locations, rather than the selected team's home city, handle road and
# neutral-site games correctly. Unknown locations explicitly fall back to UTC.
VENUE_TIMEZONES = {
    ('chicago','IL'): 'America/Chicago',
    ('seattle','WA'): 'America/Los_Angeles',
    ('brooklyn','NY'): 'America/New_York',
    ('new york','NY'): 'America/New_York',
    ('college park','GA'): 'America/New_York',
    ('atlanta','GA'): 'America/New_York',
    ('phoenix','AZ'): 'America/Phoenix',
    ('uncasville','CT'): 'America/New_York',
    ('los angeles','CA'): 'America/Los_Angeles',
    ('washington','DC'): 'America/New_York',
    ('las vegas','NV'): 'America/Los_Angeles',
    ('indianapolis','IN'): 'America/Indiana/Indianapolis',
    ('san francisco','CA'): 'America/Los_Angeles',
    ('baltimore','MD'): 'America/New_York',
    ('boston','MA'): 'America/New_York',
    ('dallas','TX'): 'America/Chicago',
    ('minneapolis','MN'): 'America/Chicago',
    ('arlington','TX'): 'America/Chicago',
    ('san jose','CA'): 'America/Los_Angeles',
    ('vancouver','BC'): 'America/Vancouver',
    ('fairfax','VA'): 'America/New_York',
    ('portland','OR'): 'America/Los_Angeles',
    ('toronto','ON'): 'America/Toronto',
}

def game_dates(summary, event):
    competition = (event.get('competitions') or [{}])[0]
    header = (summary.get('header',{}).get('competitions') or [{}])[0]
    stamp = header.get('date') or event.get('date') or ''
    venue = summary.get('gameInfo',{}).get('venue') or competition.get('venue') or {}
    address = venue.get('address') or {}
    key = (str(address.get('city','')).strip().casefold(),str(address.get('state','')).strip().upper())
    zone = VENUE_TIMEZONES.get(key)
    try:
        start = datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if start.tzinfo is None: raise ValueError('Source has no timezone')
        utc = start.astimezone(timezone.utc)
        try:
            local = utc.astimezone(ZoneInfo(zone)) if zone else utc
        except ZoneInfoNotFoundError:
            zone = None
            local = utc
        return dict(date=local.date().isoformat(),date_utc=utc.date().isoformat(),
                    date_timezone=zone or 'UTC',date_basis='venue_local' if zone else 'utc_fallback',
                    start_time_utc=utc.isoformat().replace('+00:00','Z'))
    except (ValueError,TypeError):
        return dict(date=stamp[:10],date_utc=None,date_timezone=None,
                    date_basis='source_date',start_time_utc=None)

# These are source-text categories, not diagnoses or incident counts. Keep
# ambiguous health reports unknown rather than guessing injury versus illness.
INJURY_REASON = re.compile(r"\b(?:injur\w*|arm|thigh|adductor|pinky|dislocat\w*|head|face|facial|heel|shin|pelvi\w*|tibia\w*|fibula\w*|tendon\w*|bicep\w*|tricep\w*|metatarsal\w*|patella\w*|oblique\w*|glute\w*|menisc\w*|ankle|back|knee|acl|mcl|pcl|lcl|concussion|hamstring|shoulder|wrist|hand|finger|thumb|nose|eye|toe|foot|achilles|calf|groin|hip|quad\w*|elbow|rib\w*|leg|neck|abdomen|abdominal|chest|sprain\w*|strain\w*|fractur\w*|contusion|laceration|soreness)\b", re.I)
OTHER_REASONS = {"COACH'S DECISION", 'NOT WITH TEAM', 'PERSONAL', 'PERSONAL REASONS',
                 'REST', 'LEAGUE SUSPENSION', 'SUSPENDED BY LEAGUE', 'PLAYER SUSPENDED', 'SUSPENSION',
                 'OVERSEAS',
                 'NOT WITH TEAM - PREGNANCY', 'NOT INJURY RELATED', 'NON-INJURY RELATED'}

def classify_dnp(reason):
    normalized = re.sub(r'\s+',' ',str(reason or '').upper().replace('’',"'")).strip()
    normalized = re.sub(r'^DNP\s*[-:]\s*','',normalized)
    normalized = re.sub(r'^INJURY\s*/\s*ILLNESS\s*[-:]\s*(?=\S)','',normalized)
    detail_without_umbrella=re.sub(r'INJURY\s*/\s*ILLNESS','',normalized)
    if re.search(r'[A-Z]',detail_without_umbrella):normalized=detail_without_umbrella.strip(' -:;')
    if not normalized:
        return dict(dnp_category='unknown',health_dnp=False,classification_note='No source reason reported')
    if normalized in {'DID NOT PLAY','DID NOT DRESS','INACTIVE','DNP'}:
        return dict(dnp_category='unknown',health_dnp=False,classification_note='Participation status does not establish an absence reason')
    known_nonmedical=bool(re.match(r"^(?:COACH(?:\s*'\s*S|ES)?\s+DECISION|PERSONAL(?: REASONS)?|(?:N/?A[;:\s]+)?REST)(?:\s*[-;:]|$)",normalized))
    if known_nonmedical or normalized in OTHER_REASONS or re.search(r'\b(?:NOT|NON)[ -]INJURY[ -]RELATED\b',normalized):
        return dict(dnp_category='other',health_dnp=False,classification_note='Reported non-injury reason or participation status')
    injury = bool(INJURY_REASON.search(normalized))
    illness = bool(re.search(r'\b(?:ILLNESS|ILL|SICKNESS|FLU|COVID(?:-19)?)\b',normalized))
    if (injury and illness) or normalized in {'COLLAPSED LUNG','RETURN TO COMPETITION RECONDITIONING'}:
        return dict(dnp_category='unknown',health_dnp=True,classification_note='Health-related source reason; injury versus illness is unspecified')
    if illness:
        return dict(dnp_category='illness',health_dnp=True,classification_note='Illness reported in the source')
    if injury:
        return dict(dnp_category='injury',health_dnp=True,classification_note='Injury or body-site reason reported in the source')
    return dict(dnp_category='unknown',health_dnp=False,classification_note='Unrecognized source reason; review required')

def dnp_counts(players):
    counts = {category:0 for category in ('injury','illness','other','unknown')}
    health_unspecified = 0
    for player in players:
        if player['played'] is not False: continue
        category = player.get('dnp_category') or 'unknown'
        counts[category] += 1
        health_unspecified += int(category == 'unknown' and player.get('health_dnp',False))
    return dict(injury_dnp=counts['injury'],illness_dnp=counts['illness'],
                other_dnp=counts['other'],unknown_dnp=counts['unknown'],
                health_unspecified_dnp=health_unspecified)

def parse_players(summary, team_id):
    block = next((b for b in summary.get('boxscore',{}).get('players',[]) if str(b.get('team',{}).get('id')) == str(team_id)), None)
    if block is None: raise ValueError('Team player box score is missing')
    players = {}
    for group in block.get('statistics',[]):
        labels = group.get('labels') or group.get('names') or []
        for row in group.get('athletes',[]):
            athlete = row.get('athlete',{})
            stats = dict(zip([str(x).upper() for x in labels], row.get('stats',[])))
            raw_min = stats.get('MIN', stats.get('MINUTES'))
            mp = minutes(raw_min)
            dnp = row.get('didNotPlay')
            # Missing or contradictory evidence does not establish absence.
            played = False if dnp is True and mp is None else True if dnp is not True and mp is not None else None
            reason = str(row.get('reason') or '')
            classification = classify_dnp(reason) if played is False else dict(dnp_category=None,health_dnp=False,classification_note=None)
            injury = classification['dnp_category'] == 'injury'
            pid = str(athlete.get('id') or athlete.get('displayName','Unknown'))
            players[pid] = dict(
                id=pid,
                name=athlete.get('displayName','Unknown'),
                position=athlete.get('position',{}).get('abbreviation','—'),
                minutes=mp if played else None,
                played=played,reason=reason,reported_minutes=raw_min,source_did_not_play=dnp,
                participation_status='played' if played is True else 'absent' if played is False else 'unknown',
                injury_dnp=injury,
                **classification,
                starter=bool(row.get('starter')),
                points=stats.get('PTS',stats.get('POINTS','—'))
                )

         
    if not players: raise ValueError('No player rows returned')
    if not any(p['played'] is True for p in players.values()):raise ValueError('No confirmed player participation available')
    return list(players.values())

def collect(team, season, season_type=2, limit=10, progress=None, refresh=False):
    try:
        schedule = fetch(f'/teams/{team}/schedule', {'season':season,'seasontype':season_type}, refresh)
    except requests.HTTPError as error:
        # ESPN may not publish a schedule until closer to a future season.
        if season <= date.today().year or error.response is None or error.response.status_code != 404:
            raise
        team_info = next((t for t in teams() if str(t.get('id')) == str(team) or t.get('abbreviation','').lower() == str(team).lower()), {'id':str(team),'displayName':'WNBA team'})
        schedule = {'team':team_info,'events':[]}
    team_info = schedule.get('team',{})
    tid = str(team_info.get('id',''))
    events=[]
    for event in schedule.get('events',[]):
        comp = event.get('competitions',[{}])[0]
        if str(event.get('season',{}).get('year') or event.get('date','')[:4]) != str(season): continue
        if int(event.get('seasonType',{}).get('type',season_type)) != season_type: continue
        # Cup qualifying games count; the separately flagged Cup final does not.
        if comp.get('type',{}).get('type') == 'commissioners-cup': continue
        if comp.get('status',{}).get('type',{}).get('completed'):
            events.append(event)
    events.sort(key=lambda e:(e.get('date',''), e['id']))
    total=len(events)
    events = events[:limit] if limit else events
    games=[]; errors=[]
    for n,event in enumerate(events,1):
        if progress: progress(n-1,len(events))
        try:
            summary=fetch('/summary',{'event':event['id']},refresh)
            header=summary.get('header',{})
            if header.get('id') is not None and str(header['id'])!=str(event['id']):raise ValueError('Box-score source returned a different game')
            if header.get('season',{}).get('year') is not None and str(header['season']['year'])!=str(season):raise ValueError('Box-score source returned a different season')
            comp=event['competitions'][0]
            sides=comp.get('competitors',[])
            own=next((x for x in sides if str(x.get('team',{}).get('id'))==tid),None)
            if own is None: raise ValueError('Team missing from schedule matchup')
            opponent=next(x for x in sides if x is not own)
            players=parse_players(summary,tid)
            played=[p for p in players if p['played']]
            min_values=[p['minutes'] for p in played]
            # Use explicit game period rather than noisy summed player minutes.
            period=summary.get('header',{}).get('competitions',[{}])[0].get('status',{}).get('period') or comp.get('status',{}).get('period')
            ot=max(0,int(period)-(2 if int(season)<2006 else 4)) if period else None
            score=lambda side: str(side.get('score',{}).get('displayValue','')) if isinstance(side.get('score'),dict) else str(side.get('score',''))
            source_team=next((b.get('team',{}) for b in summary.get('boxscore',{}).get('players',[]) if str(b.get('team',{}).get('id'))==tid),{})
            game=dict(id=event['id'],team_name=source_team.get('displayName'),team_code=source_team.get('abbreviation'),box_score_status='available',**game_dates(summary,event),opponent=opponent['team'].get('abbreviation',''),opponent_name=opponent['team'].get('displayName',''),home_away=own.get('homeAway'),result='W' if own.get('winner') is True else 'L' if own.get('winner') is False else '—',score=f'{score(own)} – {score(opponent)}',rostered=len(players),entered=len(played),dnp=sum(p['played'] is False for p in players),participation_unknown=sum(p['played'] is None for p in players),**dnp_counts(players),minutes=round(sum(min_values),2) if played else None,overtime=ot,in_game_injuries=None,players=players,source=f'https://www.espn.com/wnba/boxscore/_/gameId/{event["id"]}')
            from wnba_official_reports import enrich_game
            games.append(enrich_game(game,summary,event,team_info))
        except (requests.RequestException, ValueError, KeyError, IndexError, StopIteration) as error:
            errors.append(dict(game_id=event['id'],message=str(error)))
            # An unavailable box score must not discard independently available
            # official injury evidence for a completed scheduled game.
            comp=event['competitions'][0]
            sides=comp.get('competitors',[])
            own=next((x for x in sides if str(x.get('team',{}).get('id'))==tid),{})
            opponent=next((x for x in sides if str(x.get('team',{}).get('id'))!=tid),{})
            if own and opponent:
                game=dict(id=event['id'],**game_dates({},event),opponent=opponent['team'].get('abbreviation',''),opponent_name=opponent['team'].get('displayName',''),home_away=own.get('homeAway'),result='—',score='Unavailable',rostered=None,entered=None,dnp=None,participation_unknown=None,injury_dnp=None,illness_dnp=None,other_dnp=None,unknown_dnp=None,health_unspecified_dnp=None,minutes=None,overtime=None,in_game_injuries=None,players=[],box_score_status='unavailable',box_score_note=str(error),source=f'https://www.espn.com/wnba/boxscore/_/gameId/{event["id"]}')
                from wnba_official_reports import enrich_game
                games.append(enrich_game(game,{},event,team_info))
        time.sleep(.15)
    if progress: progress(len(events),len(events))
    from season_coverage import for_season
    return dict(team=team_info,season=season,season_coverage=for_season(season),season_type=season_type,games=games,completed_games=total,requested_games=len(events),errors=errors,fetched_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),boxscore_loaded_games=sum(g['box_score_status']=='available' for g in games),source='ESPN WNBA + official WNBA report snapshots' if any(g['official_report']['status']=='available' for g in games) else 'ESPN WNBA (official report coverage unavailable)',schema_version=3,notes=['Rostered means players listed in each game box score; dressed availability is not verified.','Official pregame snapshots are separate from actual participation; missing coverage is unavailable, not zero. Pre-2026 official archive coverage is not verified.', 'DNP reasons are categorized as injury, illness, other or unknown. Mixed injury/illness and unspecified health reasons remain unknown. These are not diagnoses or in-game injury events.','Dates use venue-local time; unknown venue timezones use explicitly labeled UTC.','200 player-minutes in regulation; 25 per overtime. Rounded source minutes may vary.'])

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--team',default='ind');p.add_argument('--season',type=int,default=2025);p.add_argument('--limit',type=int,default=10);p.add_argument('--postseason',action='store_true');p.add_argument('--output',default='data/snapshot.json');args=p.parse_args()
    data=collect(args.team,args.season,3 if args.postseason else 2,args.limit,lambda a,b:print(f'{a}/{b} games',flush=True))
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(data,indent=2));print(f'Saved {len(data["games"])} games; {len(data["errors"])} errors to {out}')
