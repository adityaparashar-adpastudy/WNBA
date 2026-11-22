"""Latest published source lists, never joined to historical game observations.

An outlet listing is 'reported', not primary confirmation of a diagnosis.
Retrieval time does not establish that a row is current or a player still injured.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import re
from threading import Lock
import time
import requests
from collector import classify_dnp

ESPN='https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/injuries'
ESPN_PAGE='https://espn.com/wnba/injuries'
ACTION='https://www.actionnetwork.com/wnba/injuries'
OFFICIAL='https://www.wnba.com/wnba-injury-report'
_cache=None
_lock=Lock()

def record(source,team,player,status,detail,reported_at,source_url,player_id='',body_part='',started_at=''):
    classification=classify_dnp(body_part or detail)
    try:
        published=datetime.fromisoformat(str(reported_at).replace('Z','+00:00'))
        age=(datetime.now(timezone.utc)-published.astimezone(timezone.utc)).total_seconds()/86400
        stale=age>7
    except (ValueError,TypeError):stale=None
    return dict(source=source,team=team,player=player,player_id=player_id,status=status,injury_detail=detail,injury_body_part=body_part,side='',date_reported=reported_at,started_at=started_at,season='',games_missed=None,return_date=None,source_url=source_url,confidence='reported',primary_verification='not_verified',category=classification['dnp_category'],stale=stale,offseason_or_overseas='not_verified',evidence_scope='latest_source_listing_not_game_evidence')

def parse_espn(data):
    if data.get('status')!='success' or not isinstance(data.get('injuries'),list):raise ValueError('Unrecognized ESPN injury response')
    rows=[]
    for team in data['injuries']:
        for item in team.get('injuries',[]):
            athlete=item.get('athlete') or {};detail=item.get('details') or {}
            if not athlete.get('displayName'):continue
            body=detail.get('type') or ''
            row=record('ESPN',team.get('displayName',''),athlete['displayName'],item.get('status',''),item.get('shortComment') or body,item.get('date'),ESPN_PAGE,str(athlete.get('id','')),body_part=body if re.fullmatch(r'(?:ankle|back|knee|hamstring|shoulder|wrist|hand|finger|thumb|nose|eye|toe|foot|achilles|calf|groin|hip|quad|elbow|rib|leg|neck|abdomen|chest)',body,re.I) else '')
            row['category']=classify_dnp(body or item.get('shortComment',''))['dnp_category']
            row['source_reason']=body
            rows.append(row)
    return rows,data.get('timestamp')

def parse_action(html):
    match=re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',html,re.S)
    if not match:raise ValueError('Action Network structured data unavailable')
    data=json.loads(match[1])['props']['pageProps']
    if data.get('league')!='wnba' or not isinstance(data.get('injuries'),list):raise ValueError('Unrecognized Action Network injury response')
    rows=[]
    for item in data['injuries']:
        player=(item.get('player') or {}).get('full_name');team=(item.get('team') or {}).get('full_name','')
        if not player:continue
        # Keep both independently reported strings; never replace status with our interpretation.
        detail=' | '.join(str(item.get(k) or '') for k in ('comment','description')).strip(' |')
        rows.append(record('Action Network',team,player,item.get('status',''),detail,item.get('updated_at'),ACTION,started_at=item.get('started_at','')))
    return rows,None

def _load(name,url,parser):
    now=datetime.now(timezone.utc).isoformat()
    try:
        response=requests.get(url,timeout=(3,10),headers={'User-Agent':'WNBA-Research-Dashboard/1.0'})
        response.raise_for_status();rows,source_updated=parser(response.json() if name=='ESPN' else response.text)
        return dict(name=name,source_url=ESPN_PAGE if name=='ESPN' else ACTION,status='available',retrieved_at=now,source_updated_at=source_updated,records=rows,note='Latest source listing; row dates may be old. Primary-source verification and game-by-game reconciliation are required before research logging.')
    except (requests.RequestException,ValueError,KeyError,TypeError) as error:
        return dict(name=name,source_url=ESPN_PAGE if name=='ESPN' else ACTION,status='unavailable',retrieved_at=now,records=[],note='Source could not be retrieved or parsed; this is not zero injuries.')

def latest():
    global _cache
    with _lock:
        if _cache and time.monotonic()-_cache[0]<300:return _cache[1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            espn=pool.submit(_load,'ESPN',ESPN,parse_espn)
            action=pool.submit(_load,'Action Network',ACTION,parse_action)
            sources=[dict(name='WNBA',source_url=OFFICIAL,status='game_snapshots_only',records=[],note='Official dated pregame PDFs are shown with the selected games where available. No latest-page snapshot is loaded here. Pre-2026 PDF archive coverage is unverified.'),espn.result(),action.result()]
        data=dict(scope='latest_source_listings',historical_join=False,sources=sources,note='Independent source rows, not a verified injury registry. Do not sum duplicate player listings or use this list as evidence for a selected historical season. Team/league statements take precedence; no automatic confirmation from outlet news. Games missed and actual return dates are unreconciled and remain blank.')
        _cache=(time.monotonic(),data)
        return data
