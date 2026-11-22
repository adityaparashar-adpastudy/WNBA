import json
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
from current_injuries import parse_action,parse_espn,_load
from season_coverage import catalog
from app import app

class SourceTests(unittest.TestCase):
    def test_espn_reason_and_unreconciled_fields(self):
        data={'status':'success','timestamp':'2026-11-22T00:00Z','injuries':[{'displayName':'Team','injuries':[{'athlete':{'id':'123','displayName':'Player Name'},'details':{'type':"Coach's Decision",'returnDate':'2027-01-01'},'status':'Out','date':'2025-05-01T00:00Z','shortComment':'Coach decision'}]}]}
        rows,stamp=parse_espn(data);r=rows[0]
        self.assertEqual(r['category'],'other');self.assertEqual(r['injury_body_part'],'')
        self.assertEqual(r['confidence'],'reported');self.assertIsNone(r['return_date']);self.assertIsNone(r['games_missed']);self.assertTrue(r['stale']);self.assertEqual(r['season'],'')
    def test_action_preserves_conflicting_status_strings(self):
        data={'props':{'pageProps':{'league':'wnba','injuries':[{'player':{'full_name':'Full Name'},'team':{'full_name':'Team'},'status':'day_to_day','comment':'Name day-to-day with knee','description':'Team listed player as Out.','updated_at':'2025-05-25T00:00Z'}]}}}
        rows,_=parse_action('<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>')
        self.assertEqual(rows[0]['status'],'day_to_day');self.assertIn('Out',rows[0]['injury_detail']);self.assertEqual(rows[0]['category'],'injury');self.assertIsNone(rows[0]['games_missed'])
        with self.assertRaises(ValueError):parse_action('<p>No report</p>')
    def test_source_failures_do_not_become_available_zero(self):
        with patch('current_injuries.requests.get',return_value=Mock(json=lambda:{'error':'bad'},raise_for_status=lambda:None)):
            r=_load('ESPN','https://example.org',parse_espn)
        self.assertEqual(r['status'],'unavailable');self.assertIn('not zero',r['note'])
    def test_all_dropdown_years_audited_and_empty_seasons_hidden(self):
        data=app.test_client().get('/api/seasons').get_json()
        self.assertEqual(set(catalog()['seasons']),set(map(str,range(1997,2028))))
        self.assertEqual(data['available_seasons'],list(range(2026,2012,-1)))
        self.assertTrue(all(catalog()['seasons'][str(y)]['sample_boxscores_available']>0 for y in data['available_seasons']))
    def test_current_source_endpoint_is_explicitly_separate(self):
        with patch('current_injuries.latest',return_value={'historical_join':False,'sources':[]}):
            data=app.test_client().get('/api/current-injuries').get_json()
        self.assertFalse(data['historical_join'])

if __name__=='__main__':unittest.main()

class HistoricalTimingTests(unittest.TestCase):
    def test_half_based_overtime_and_historical_team_identity(self):
        from collector import collect
        for year,period in ((2005,3),(2006,5)):
            event={'id':'1','date':f'{year}-06-10','season':{'year':year},'competitions':[{'status':{'type':{'completed':True},'period':period},'competitors':[{'team':{'id':'3'},'score':'80','winner':True},{'team':{'id':'5'},'score':'75'}]}]}
            summary={'boxscore':{'players':[{'team':{'id':'3','displayName':'Detroit Shock','abbreviation':'DET'},'statistics':[{'labels':['MIN'],'athletes':[{'athlete':{'id':'1','displayName':'Player'},'stats':['40']}]}]}]}}
            with patch('collector.fetch',side_effect=[{'team':{'id':'3'},'events':[event]},summary]),patch('collector.time.sleep'):
                game=collect('3',year)['games'][0]
            self.assertEqual(game['overtime'],1);self.assertEqual(game['team_name'],'Detroit Shock')
