"""Local Flask dashboard; run python3 app.py."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import secrets
from threading import Lock
import time
from flask import Flask, jsonify, render_template, request
from collector import collect, teams

app=Flask(__name__)
ROOT=Path(__file__).parent
pool=ThreadPoolExecutor(max_workers=2)
jobs={}; lock=Lock()

@app.get('/')
def index(): return render_template('index.html')

def season_options():
    current=date.today().year
    return dict(min_season=1997,current_season=current,max_season=current+1)

@app.get('/api/seasons')
def seasons(): return jsonify(season_options())

@app.get('/api/teams')
def catalog(): return jsonify(teams=teams(),**season_options())

@app.get('/api/snapshot')
def snapshot():
    path=ROOT/'data'/'snapshot.json'
    if not path.exists(): return jsonify(error='No saved data yet. Choose a team and load games.'),404
    return jsonify(json.loads(path.read_text()))

@app.post('/api/query')
def query():
    payload=request.get_json(silent=True) or {}
    try:
        team=str(payload.get('team','ind')).lower()
        if not team.isalnum() or len(team)>12: raise ValueError('Invalid team')
        season=int(payload.get('season',2025));limit=int(payload.get('limit',10));kind=int(payload.get('season_type',2))
        if not 1997<=season<=season_options()['max_season'] or limit not in (5,10,20,0) or kind not in (2,3): raise ValueError('Invalid season, game limit, or season type')
    except (ValueError,TypeError) as e: return jsonify(error=str(e)),400
    with lock:
        for old in [k for k,v in jobs.items() if time.time()-v['created']>3600 and v['status']!='running']: jobs.pop(old)
        if sum(x['status']=='running' for x in jobs.values())>=2: return jsonify(error='Two queries are running. Please wait for one to finish.'),429
        jid=secrets.token_hex(12);jobs[jid]=dict(status='running',done=0,total=0,created=time.time())
    def work():
        try:
            def progress(done,total):
                with lock: jobs[jid].update(done=done,total=total)
            result=collect(team,season,kind,limit,progress,bool(payload.get('refresh',False)))
            with lock: jobs[jid].update(status='done',data=result)
        except Exception as e:
            with lock: jobs[jid].update(status='error',error=f'Data request failed: {e}')
    pool.submit(work)
    return jsonify(job_id=jid),202

@app.get('/api/jobs/<jid>')
def job(jid):
    with lock: result=dict(jobs.get(jid,{}))
    if not result:return jsonify(error='Query not found'),404
    return jsonify(result)

if __name__=='__main__': app.run(host='127.0.0.1',port=5050,debug=False)
