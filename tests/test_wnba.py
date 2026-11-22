from datetime import date
import os
import tempfile
import requests
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collector import minutes, parse_players, collect, fetch
from app import app

class MetricsTests(unittest.TestCase):
    def fixture(self):
        return {'boxscore':{'players':[{'team':{'id':'5'},'statistics':[{'labels':['MIN','PTS'],'athletes':[
            {'athlete':{'id':'1','displayName':'Player A'},'stats':['0','0']},
            {'athlete':{'id':'2','displayName':'Player B'},'stats':[],'didNotPlay':True,'reason':"COACH'S DECISION"},
            {'athlete':{'id':'3','displayName':'Player C'},'stats':[],'didNotPlay':True,'reason':'LEFT ANKLE INJURY'},
            {'athlete':{'id':'4','displayName':'Player D'},'stats':[],'didNotPlay':True},
        ]}]}]}}
    def test_minutes(self):
        self.assertAlmostEqual(minutes('1:30'),1.5)
        self.assertIsNone(minutes('--'))
        self.assertEqual(minutes('0'),0)
    def test_dnp_evidence_and_zero_minutes(self):
        rows=parse_players(self.fixture(),'5')
        self.assertTrue(rows[0]['played'])
        self.assertFalse(rows[1]['injury_dnp'])
        self.assertTrue(rows[2]['injury_dnp'])
        self.assertFalse(rows[3]['injury_dnp'])
    def test_duplicate_groups_do_not_inflate_roster(self):
        fixture=self.fixture();fixture['boxscore']['players'][0]['statistics']*=2
        self.assertEqual(len(parse_players(fixture,'5')),4)
    def test_missing_team_is_failure(self):
        with self.assertRaises(ValueError):parse_players(self.fixture(),'9')
    @patch('collector.time.sleep')
    @patch('collector.fetch')
    def test_filters_cup_and_failed_games(self,fetch,sleep):
        def event(gid,kind='standard'):
            return {'id':gid,'date':'2025-05-17','season':{'year':2025},'seasonType':{'type':2},'competitions':[{'status':{'type':{'completed':True},'period':5},'type':{'type':kind},'competitors':[{'team':{'id':'5'},'winner':True,'score':'80'},{'team':{'id':'19','abbreviation':'CHI'},'score':'70'}]}]}
        fetch.side_effect=[{'team':{'id':'5'},'events':[event('1'),event('2','commissioners-cup'),event('3')]},self.fixture(),ValueError('missing game')]
        result=collect('5',2025,limit=0)
        self.assertEqual(result['completed_games'],2)
        self.assertEqual(len(result['games']),1)
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(result['games'][0]['overtime'],1)
    def test_snapshot_consistency(self):
        data=json.loads((Path(__file__).resolve().parents[1]/'data/snapshot.json').read_text())
        self.assertTrue(data['games'])
        for g in data['games']:
            self.assertEqual(g['entered']+g['dnp'],g['rostered'])
            self.assertLessEqual(g['injury_dnp'],g['dnp'])
            self.assertIsNone(g['in_game_injuries'])
    def test_api_validation_and_page(self):
        client=app.test_client()
        self.assertEqual(client.get('/').status_code,200)
        self.assertEqual(client.get('/api/snapshot').status_code,200)
        for payload in ({'team':'../etc'},{'season':1900},{'limit':82},{'season_type':4}):
            self.assertEqual(client.post('/api/query',json=payload).status_code,400)
        self.assertEqual(client.get('/api/jobs/missing').status_code,404)
class FutureSeasonTests(unittest.TestCase):
    def test_season_catalog_tracks_server_year(self):
        data=app.test_client().get('/api/seasons').get_json()
        self.assertEqual(data['current_season'],date.today().year)
        self.assertEqual(data['max_season'],date.today().year+1)
        self.assertEqual(data['min_season'],1997)

    @patch('app.pool.submit',side_effect=lambda fn:fn())
    @patch('app.collect')
    def test_next_year_accepted_and_later_year_rejected(self,collector,submit):
        collector.return_value={'games':[],'errors':[],'completed_games':0}
        client=app.test_client()
        response=client.post('/api/query',json={'season':date.today().year+1})
        self.assertEqual(response.status_code,202)
        job=client.get('/api/jobs/'+response.get_json()['job_id']).get_json()
        self.assertEqual(job['status'],'done')
        self.assertEqual(collector.call_args.args[1],date.today().year+1)
        self.assertEqual(client.post('/api/query',json={'season':date.today().year+2}).status_code,400)

    @patch('collector.teams',return_value=[{'id':'5','displayName':'Indiana Fever'}])
    @patch('collector.fetch')
    def test_unpublished_future_schedule_is_empty(self,fetcher,teams):
        response=requests.Response();response.status_code=404
        fetcher.side_effect=requests.HTTPError(response=response)
        result=collect('5',date.today().year+1)
        self.assertEqual(result['games'],[])
        self.assertEqual(result['errors'],[])
        with self.assertRaises(requests.HTTPError):collect('5',2025)

    @patch('collector.fetch')
    def test_wrong_year_fallback_is_never_shown(self,fetcher):
        fetcher.return_value={'team':{'id':'5'},'events':[{'id':'old','date':'2025-05-17','competitions':[{'status':{'type':{'completed':True}}}]}]}
        result=collect('5',date.today().year+1)
        self.assertEqual(result['completed_games'],0)
        self.assertEqual(fetcher.call_count,1)

    @patch('collector.requests.get')
    def test_schedule_and_catalog_cache_expire(self,get):
        get.return_value.json.return_value={'updated':True}
        with tempfile.TemporaryDirectory() as directory,patch('collector.CACHE',Path(directory)):
            for endpoint in ['/teams/5/schedule','/teams']:
                fetch(endpoint)
                count=get.call_count
                fetch(endpoint)
                self.assertEqual(get.call_count,count)
                for cache in Path(directory).glob('*.json'):os.utime(cache,(0,0))
                fetch(endpoint)
                self.assertEqual(get.call_count,count+1)

if __name__=='__main__':unittest.main()
