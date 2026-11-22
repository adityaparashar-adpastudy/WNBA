"""Official WNBA injury-report snapshots, joined without inventing final availability."""
from datetime import datetime, timedelta
from functools import lru_cache
from io import BytesIO
import re
import unicodedata
from time import monotonic
from zoneinfo import ZoneInfo
import requests
from pypdf import PdfReader
from pypdf.errors import PyPdfError


ET = ZoneInfo('America/New_York')
TEAM_CODES = {'Atlanta Dream':'ATL','Chicago Sky':'CHI','Connecticut Sun':'CON','Dallas Wings':'DAL','Golden State Valkyries':'GS','Indiana Fever':'IND','Las Vegas Aces':'LV','Los Angeles Sparks':'LA','Minnesota Lynx':'MIN','New York Liberty':'NY','Phoenix Mercury':'PHX','Portland Fire':'POR','Seattle Storm':'SEA','Toronto Tempo':'TOR','Washington Mystics':'WSH'}
REASON_PREFIX = re.compile(r'^(Injury\s*/\s*Illness\s*[-:]|Concussion\s+Protocol|Coach[’\']?s\s+Decision|Development|Pregnancy|G\s+League|Return\s+to\s+Competition|Not\s+With\s+Team|Personal|Rest|Suspension|League\s+Suspension|Other)', re.I)
STATUSES = {'Out','Questionable','Doubtful','Probable','Available'}

def clean(text):
    return re.sub(r'\s+', ' ', text).strip().replace('Two- Way','Two-Way')

def name_key(name):
    text = unicodedata.normalize('NFKD', name or '')
    return re.sub(r'[^a-z0-9]', '', text.encode('ascii','ignore').decode().lower())

def report_category(reason):
    # Injury/Illness is a report section heading, not evidence of both conditions.
    detail = re.sub(r'^Injury\s*/\s*Illness\s*[-–:]?\s*','',reason,flags=re.I)
    from collector import classify_dnp
    return classify_dnp(detail)['dnp_category']

def parse_report(content, source_url):
    reader = PdfReader(BytesIO(content))
    plain = reader.pages[0].extract_text()
    match = re.search(r'Injury\s+Report:\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}:\d{2})\s*([AP]M)',plain,re.I)
    if not match: raise ValueError('Unrecognized WNBA report timestamp')
    date_format = '%m/%d/%y' if len(match[1].split('/')[-1])==2 else '%m/%d/%Y'
    timestamp = datetime.strptime(f'{match[1]} {match[2]} {match[3].upper()}',date_format+' %I:%M %p').replace(tzinfo=ET)
    anchors, reason_lines = [], []
    columns = None
    for page_no,page in enumerate(reader.pages):
        words=[]
        def visit(text,cm,tm,font,size):
            if text.strip():
                x=tm[4]*cm[0]+tm[5]*cm[2]+cm[4]
                y=float(page.mediabox.height)-(tm[4]*cm[1]+tm[5]*cm[3]+cm[5])
                words.append(dict(x=x,y=y,text=clean(text)))
        page.extract_text(visitor_text=visit)
        headings={}
        header_y=next((w['y'] for w in words if w['text'].split()[0]=='Matchup' and w['y']<190),None)
        for word in words:
            for heading in ('Team','Player','Current','Reason','Matchup'):
                if header_y is not None and word['text'].split()[0]==heading and abs(word['y']-header_y)<=2:headings[heading]=word
        if len(headings)==5:
            columns={key:value['x']-2 for key,value in headings.items()}
            top=max(value['y'] for value in headings.values())+3
        elif columns:
            top=75
        else:raise ValueError('Unrecognized WNBA report table columns')
        lines={}
        for word in words:
            if not top<word['y']<float(page.mediabox.height)-35:continue
            key=round(word['y']/2)*2
            lines.setdefault(key,[]).append(word)
        page_anchors=[]
        for y,words_in_line in sorted(lines.items()):
            fields={'date':[],'matchup':[],'team':[],'name':[],'status':[],'reason':[]}
            for w in sorted(words_in_line,key=lambda w:w['x']):
                x=w['x']
                if x>=columns['Reason']:key='reason'
                elif x>=columns['Current']:key='status'
                elif x>=columns['Player']:key='name'
                elif x>=columns['Team']:key='team'
                elif x>=columns['Matchup']:key='matchup'
                elif re.fullmatch(r'\d{2}/\d{2}/\d{4}',w['text']):key='date'
                else:continue
                fields[key].append(w['text'])
            fields={k:clean(' '.join(v)) for k,v in fields.items()}
            position=page_no*10000+y
            if fields['status'] in STATUSES or fields['reason']=='NOT YET SUBMITTED':
                page_anchors.append(dict(position=position,**fields))
            if fields['reason'] and fields['reason']!='NOT YET SUBMITTED':
                reason_lines.append(dict(position=position,text=fields['reason']))
        anchors.extend(page_anchors)
    actual=[a for a in anchors if a['status'] in STATUSES]
    starts=[line for line in reason_lines if
            (REASON_PREFIX.match(line['text']) and not re.match(r'^Concussion\s+Protocol',line['text'],re.I))
            or ((line['text']=='-' or re.fullmatch(r'(?:Concussion\s+Protocol|Injury\s*/\s*Illness)',line['text'],re.I))
                and any(abs(a['position']-line['position'])<=2 for a in actual))]
    # Fail closed if a report layout cannot be reconciled. Never silently drop a player.
    if len(actual)!=len(starts):
        raise ValueError(f'WNBA report rows do not reconcile ({len(actual)} players, {len(starts)} reasons)')
    records=[];not_submitted=[];matchups=set();current_date=current_matchup=current_team=''
    for a in anchors:
        if a['date']:current_date=datetime.strptime(a['date'],'%m/%d/%Y').date().isoformat()
        if a['matchup']:current_matchup=a['matchup']
        if a['team']:current_team=a['team']
        if not current_date or not current_matchup:
            raise ValueError('WNBA report row lacks an unambiguous date or matchup')
        if current_team not in TEAM_CODES:
            # Some official WNBA PDFs also contain unsubmitted NBA summer-league
            # matchups. They are outside this league, never WNBA zero-injury rows.
            if a['reason']=='NOT YET SUBMITTED':continue
            raise ValueError('WNBA report contains an unmapped player team')
        matchups.add((current_date,current_matchup))
        if a['reason']=='NOT YET SUBMITTED':
            not_submitted.append((current_date,current_matchup,TEAM_CODES[current_team]));continue
        index=len(records);start=starts[index]['position'];end=starts[index+1]['position'] if index+1<len(starts) else float('inf')
        reason=clean(' '.join(line['text'] for line in reason_lines if start<=line['position']<end))
        if ',' not in a['name']:raise ValueError('WNBA report player name is incomplete')
        last,first=a['name'].split(',',1)
        full_name=re.sub(r'(?<=\w)-\s+(?=\w)','-',clean(first+' '+last))
        records.append(dict(player_full_name=full_name,source_player_name=a['name'],team= current_team,
                            team_code=TEAM_CODES[current_team],game_date=current_date,matchup=current_matchup,
                            reported_status=a['status'],reported_reason=reason,category=report_category(reason),
                            report_at=timestamp.isoformat(),source_url=source_url))
    return dict(report_at=timestamp.isoformat(),source_url=source_url,records=records,
                not_submitted=not_submitted,matchups=sorted(matchups))


def snapshot_candidates(tipoff):
    local=tipoff.astimezone(ET)
    cutoff=local-timedelta(minutes=1)
    latest=cutoff.replace(minute=cutoff.minute//15*15,second=0,microsecond=0)
    choices=[latest,latest-timedelta(minutes=15),latest-timedelta(minutes=30)]
    choices += [local.replace(hour=h,minute=0,second=0,microsecond=0) for h in (20,17,13,7)]
    choices += [(local-timedelta(days=1)).replace(hour=20,minute=0,second=0,microsecond=0)]
    seen=set()
    for point in choices:
        if point>=local:continue
        url=f'https://ak-static.cms.nba.com/referee/wnba_injury/Injury-Report_{point:%Y-%m-%d_%I_%M%p}.pdf'
        if url not in seen:seen.add(url);yield url

@lru_cache(maxsize=512)
def _fetch_report(url,bucket):
    try:
        response=requests.get(url,timeout=(3,8));response.raise_for_status()
        if not response.content.startswith(b'%PDF'):return None
        return parse_report(response.content,url)
    except (requests.RequestException,ValueError,KeyError,IndexError,TypeError,PyPdfError):return None

def fetch_report(url):
    return _fetch_report(url,int(monotonic()//300))

def unavailable(note):
    return dict(status='unavailable',records=[],report_at=None,source_url=None,note=note)

def official_for_game(tipoff_iso,team,matchup):
    if not tipoff_iso:return unavailable('Game start time is unavailable; no safe pregame report match.')
    team={'CONN':'CON'}.get(team,team)
    if team not in TEAM_CODES.values():return unavailable('Team identity cannot be matched safely to the official report.')
    tipoff=datetime.fromisoformat(tipoff_iso.replace('Z','+00:00'))
    if tipoff.tzinfo is None:return unavailable('Game start timezone is missing.')
    if tipoff.year<2026:
        return unavailable('Official PDF archive coverage before 2026 has not been verified in this integration. Historical box-score DNP reasons remain partial evidence, not a complete injury count.')
    day=tipoff.astimezone(ET).date().isoformat();deadline=monotonic()+25
    for url in snapshot_candidates(tipoff):
        if monotonic()>deadline:break
        try:report=fetch_report(url)
        except (requests.RequestException,ValueError):continue
        if report is None:continue
        stamp=datetime.fromisoformat(report['report_at'])
        if not tipoff-timedelta(hours=36)<stamp<tipoff:continue
        if (day,matchup) not in [tuple(m) for m in report['matchups']]:continue
        if (day,matchup,team) in [tuple(m) for m in report['not_submitted']]:continue
        records=[dict(r) for r in report['records'] if (r['game_date'],r['matchup'],r['team_code'])==(day,matchup,team)]
        return dict(status='available',records=records,report_at=report['report_at'],source_url=url,
                    note='Selected available submitted pregame snapshot; later revisions may exist. Designations are not unique injuries or confirmed missed games.')
    return unavailable('No matching submitted official pregame report could be retrieved and parsed. Missing coverage is not zero injuries.')

def enrich_game(game,summary,event,team):
    comp=(summary.get('header',{}).get('competitions') or event.get('competitions') or [{}])[0]
    sides=comp.get('competitors') or event.get('competitions',[{}])[0].get('competitors',[])
    def code(value):return {'CONN':'CON','GS':'GSV','LV':'LVA','LA':'LAS','NY':'NYL','POR':'PDX','WSH':'WAS'}.get(value,value)
    away=next((x['team'].get('abbreviation') for x in sides if x.get('homeAway')=='away'),None)
    home=next((x['team'].get('abbreviation') for x in sides if x.get('homeAway')=='home'),None)
    stamp=comp.get('date') or event.get('date')
    report=official_for_game(stamp,team.get('abbreviation'),code(away)+'@'+code(home)) if away and home else unavailable('Matchup is unavailable for a safe report join.')
    for record in report['records']:
        matches=[p for p in game['players'] if name_key(p['name'])==name_key(record['player_full_name'])]
        player=matches[0] if len(matches)==1 else None
        record.update(player_id=player['id'] if player else None,
                      actual_participation=player['participation_status'] if player else 'box_score_unavailable' if game.get('box_score_status')=='unavailable' else 'not_listed_in_box_score',
                      reported_minutes=player['reported_minutes'] if player else None,
                      join_method='exact_normalized_name' if player else 'unmatched')
    game['official_report']=report
    game['official_report_counts']={c:sum(r['category']==c for r in report['records']) for c in ('injury','illness','other','unknown')} if report['status']=='available' else None
    return game
