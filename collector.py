"""WNBA data adapter, consolidated from the supplied ESPN season scrapers."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import requests

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba'
CACHE = Path(__file__).parent / 'data' / 'cache'
# Offline selector for the historical 2025 season; online catalog is preferred.
TEAMS_2025 = [('20','ATL','Atlanta Dream'),('19','CHI','Chicago Sky'),('18','CONN','Connecticut Sun'),('3','DAL','Dallas Wings'),('129689','GS','Golden State Valkyries'),('5','IND','Indiana Fever'),('17','LV','Las Vegas Aces'),('6','LA','Los Angeles Sparks'),('8','MIN','Minnesota Lynx'),('9','NY','New York Liberty'),('11','PHX','Phoenix Mercury'),('14','SEA','Seattle Storm'),('16','WSH','Washington Mystics')]
# Use abbreviations as route slugs, avoiding source-specific numeric IDs.
FALLBACK = [dict(id=tid, abbreviation=code, displayName=name) for tid,code,name in TEAMS_2025]

def fetch(path, params=None, refresh=False):
    key = hashlib.sha256((path + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
    file = CACHE / (key + '.json')
    if file.exists() and not refresh:
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
            m,s = str(value).split(':')
            return int(m) + float(s)/60
        return float(value)
    except (ValueError, TypeError): return None

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
            dnp = bool(row.get('didNotPlay'))
            # A numeric zero can represent rounded sub-minute participation.
            played = not dnp and mp is not None
            reason = str(row.get('reason') or '')
            # Evidence label only; this is not a count of in-game injuries.
            injury = not played and bool(re.search(r'injur|ankle|back|knee|acl|concussion|hamstring|shoulder|wrist|hand|finger|nose|eye|toe|foot|achilles|calf|groin', reason, re.I))
            pid = str(athlete.get('id') or athlete.get('displayName','Unknown'))
            players[pid] = dict(
                id=pid,
                name=athlete.get('displayName','Unknown'),
                position=athlete.get('position',{}).get('abbreviation','—'),
                minutes=mp if played else None,
                played=played,reason=reason,
                injury_dnp=injury,
                starter=bool(row.get('starter')),
                points=stats.get('PTS',stats.get('POINTS','—'))
                )

         
    if not players: raise ValueError('No player rows returned')
    return list(players.values())

def collect(team, season, season_type=2, limit=10, progress=None, refresh=False):
    schedule = fetch(f'/teams/{team}/schedule', {'season':season,'seasontype':season_type}, refresh)
    team_info = schedule.get('team',{})
    tid = str(team_info.get('id',''))
    events=[]
    for event in schedule.get('events',[]):
        comp = event.get('competitions',[{}])[0]
        if event.get('season',{}).get('year',season) != season: continue
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
            ot=max(0,int(period)-4) if period else None
            score=lambda side: str(side.get('score',{}).get('displayValue','')) if isinstance(side.get('score'),dict) else str(side.get('score',''))
            games.append(dict(id=event['id'],date=event['date'][:10],opponent=opponent['team'].get('abbreviation',''),opponent_name=opponent['team'].get('displayName',''),home_away=own.get('homeAway'),result='W' if own.get('winner') is True else 'L' if own.get('winner') is False else '—',score=f'{score(own)} – {score(opponent)}',rostered=len(players),entered=len(played),dnp=len(players)-len(played),injury_dnp=sum(p['injury_dnp'] for p in players),minutes=round(sum(min_values),2) if played else None,overtime=ot,in_game_injuries=None,players=players,source=f'https://www.espn.com/wnba/boxscore/_/gameId/{event["id"]}'))
        except (requests.RequestException, ValueError, KeyError, IndexError, StopIteration) as error:
            errors.append(dict(game_id=event['id'],message=str(error)))
        time.sleep(.15)
    if progress: progress(len(events),len(events))
    return dict(team=team_info,season=season,season_type=season_type,games=games,completed_games=total,requested_games=len(events),errors=errors,fetched_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),source='ESPN WNBA',notes=['Rostered means players listed in each game box score; dressed availability is not verified.','Injury-related DNP counts explicit reason keywords, not in-game injury events. Unspecified DNP reasons remain unclassified.','200 player-minutes in regulation; 25 per overtime. Rounded source minutes may vary.'])

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--team',default='ind');p.add_argument('--season',type=int,default=2025);p.add_argument('--limit',type=int,default=10);p.add_argument('--postseason',action='store_true');p.add_argument('--output',default='data/snapshot.json');args=p.parse_args()
    data=collect(args.team,args.season,3 if args.postseason else 2,args.limit,lambda a,b:print(f'{a}/{b} games',flush=True))
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(data,indent=2));print(f'Saved {len(data["games"])} games; {len(data["errors"])} errors to {out}')
