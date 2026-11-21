import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collector import minutes, parse_players, collect
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
if __name__=='__main__':unittest.main()
