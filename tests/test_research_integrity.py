import copy,unittest
from datetime import datetime
from unittest.mock import patch
from pypdf.errors import PdfReadError
from collector import parse_players,minutes,dnp_counts,collect
from app import app
from wnba_official_reports import parse_report,report_category,enrich_game,official_for_game,_fetch_report

class Page:
    mediabox=type('Box',(),{'height':595})()
    def __init__(self,rows):self.rows=rows
    def extract_text(self,visitor_text=None):
        if not visitor_text:return 'Injury Report: 06/10/26 05:00 PM'
        headings=[(200,115,'Matchup'),(264,115,'Team'),(425,115,'Player'),(585,115,'Current'),(666,115,'Reason')]
        for x,y,text in headings+self.rows:visitor_text(text,[1,0,0,1,0,0],[1,0,0,1,x,595-y],None,10)
class IntegrityTests(unittest.TestCase):
    def summary(self):
        return {'header':{'competitions':[{'date':'2026-06-10T23:00Z','competitors':[{'team':{'abbreviation':'CONN'},'homeAway':'away'},{'team':{'abbreviation':'TOR'},'homeAway':'home'}]}]},'boxscore':{'players':[{'team':{'id':'18'},'statistics':[{'labels':['MIN'],'athletes':[{'athlete':{'id':'1','displayName':'Brittney Griner'},'stats':['20'],'didNotPlay':False}]}]}]}}
    def report(self):
        return dict(status='available',report_at='2026-06-10T17:00:00-04:00',source_url='official.pdf',note='Selected snapshot',records=[dict(player_full_name='Brittney Griner',category='injury',reported_status='Questionable',reported_reason='Injury/Illness - Left Rib; Strain'),dict(player_full_name='Absent From Boxscore',category='injury',reported_status='Out',reported_reason='Injury/Illness - Left Ankle; Sprain')])
    def test_missing_and_conflicting_participation(self):
        s=self.summary();rows=s['boxscore']['players'][0]['statistics'][0]['athletes']
        rows.extend([{'athlete':{'id':'2','displayName':'Missing'},'stats':['--'],'didNotPlay':False},{'athlete':{'id':'3','displayName':'Contradictory'},'stats':['12'],'didNotPlay':True}])
        p=parse_players(s,'18')
        self.assertTrue(p[0]['played']);self.assertIsNone(p[1]['played']);self.assertIsNone(p[2]['played']);self.assertIsNone(p[2]['dnp_category'])
        self.assertEqual(sum(dnp_counts(p).values()),0)
    def test_invalid_minutes_are_not_exposure(self):
        for value in ('1:99','-1','nan','inf','12x','2:3'):self.assertIsNone(minutes(value))
        self.assertEqual(minutes('0'),0)
        self.assertEqual(minutes('2:30'),2.5)
    def test_all_missing_players_fail_closed(self):
        s=self.summary();s['boxscore']['players'][0]['statistics'][0]['athletes'][0]['stats']=['--']
        with self.assertRaisesRegex(ValueError,'No confirmed'):parse_players(s,'18')
    def test_umbrella_is_not_a_diagnosis(self):
        self.assertEqual(report_category('Injury/Illness - Left Ankle; Sprain'),'injury')
        self.assertEqual(report_category('Injury/Illness - Illness'),'illness')
        self.assertEqual(report_category('Injury/Illness'),'unknown')
        self.assertEqual(report_category("Coach's Decision"),'other')
    def test_report_and_participation_are_separate(self):
        s=self.summary();g=dict(players=parse_players(s,'18'))
        with patch('wnba_official_reports.official_for_game',return_value=self.report()):r=enrich_game(g,s,{},dict(abbreviation='CONN'))
        self.assertEqual(r['official_report_counts']['injury'],2)
        played,unmatched=r['official_report']['records']
        self.assertEqual(played['actual_participation'],'played');self.assertEqual(played['reported_minutes'],'20')
        self.assertEqual(unmatched['actual_participation'],'not_listed_in_box_score');self.assertIsNone(unmatched['player_id']);self.assertIsNone(unmatched['reported_minutes'])
        self.assertEqual(len(g['players']),1)
    def test_surname_only_never_joins(self):
        report=self.report();report['records']=report['records'][:1];report['records'][0]['player_full_name']='Another Griner';s=self.summary()
        with patch('wnba_official_reports.official_for_game',return_value=report):r=enrich_game(dict(players=parse_players(s,'18')),s,{},dict(abbreviation='CONN'))
        self.assertEqual(r['official_report']['records'][0]['join_method'],'unmatched')
    def test_historical_reports_explicitly_unverified(self):
        with patch('wnba_official_reports.fetch_report') as f:r=official_for_game('2025-06-10T23:00Z','CONN','CON@TOR')
        self.assertEqual(r['status'],'unavailable');f.assert_not_called()
    def test_after_tipoff_rejected(self):
        report=dict(report_at='2026-06-10T20:00:00-04:00',matchups=[('2026-06-10','CON@TOR')],not_submitted=[],records=[])
        with patch('wnba_official_reports.fetch_report',return_value=report):r=official_for_game('2026-06-10T23:00Z','CONN','CON@TOR')
        self.assertEqual(r['status'],'unavailable')
    def test_not_submitted_rejected(self):
        report=dict(report_at='2026-06-10T17:00:00-04:00',matchups=[('2026-06-10','CON@TOR')],not_submitted=[('2026-06-10','CON@TOR','CON')],records=[])
        with patch('wnba_official_reports.fetch_report',return_value=report):r=official_for_game('2026-06-10T23:00Z','CONN','CON@TOR')
        self.assertEqual(r['status'],'unavailable')
    def test_available_empty_snapshot_is_zero_designations(self):
        report=dict(report_at='2026-06-10T17:00:00-04:00',matchups=[('2026-06-10','CON@TOR')],not_submitted=[],records=[])
        with patch('wnba_official_reports.fetch_report',return_value=report):r=official_for_game('2026-06-10T23:00Z','CONN','CON@TOR')
        self.assertEqual(r['status'],'available');self.assertEqual(r['records'],[])
    def test_unavailable_count_stays_null(self):
        s=self.summary()
        with patch('wnba_official_reports.official_for_game',return_value=dict(status='unavailable',records=[])):
            r=enrich_game(dict(players=parse_players(s,'18')),s,{},dict(abbreviation='CONN'))
        self.assertIsNone(r['official_report_counts'])
    def test_pdf_row_reconciliation_and_wrapped_reason(self):
        page=Page([(24,145,'06/10/2026'),(201,145,'CON@TOR'),(265,145,'Connecticut Sun'),(426,145,'Griner, Brittney'),(587,145,'Out'),(667,138,'Injury/Illness - Left Rib;'),(667,152,'Strain'),(426,175,'Example, Player'),(587,175,'Out'),(667,175,"Coach's Decision")])
        with patch('wnba_official_reports.PdfReader',return_value=type('Reader',(),{'pages':[page]})()):r=parse_report(b'pdf','official.pdf')
        self.assertEqual(len(r['records']),2);self.assertEqual(r['records'][0]['player_full_name'],'Brittney Griner');self.assertEqual(r['records'][0]['reported_reason'],'Injury/Illness - Left Rib; Strain');self.assertEqual(r['records'][1]['category'],'other')
    def test_unknown_pdf_layout_fails_closed(self):
        page=Page([(24,145,'06/10/2026'),(201,145,'CON@TOR'),(265,145,'Connecticut Sun'),(426,145,'Griner, Brittney'),(587,145,'Out'),(667,145,'Unexpected column format')])
        with patch('wnba_official_reports.PdfReader',return_value=type('Reader',(),{'pages':[page]})()):
            with self.assertRaises(ValueError):parse_report(b'pdf','official.pdf')
    def test_malformed_pdf_is_unavailable(self):
        response=type('Response',(),{'content':b'%PDF broken','raise_for_status':lambda self:None})()
        with patch('wnba_official_reports.requests.get',return_value=response),patch('wnba_official_reports.PdfReader',side_effect=PdfReadError('bad pdf')):
            self.assertIsNone(_fetch_report('test.pdf',123))
    def test_header_team_word_cannot_be_overwritten_by_reason(self):
        page=Page([(24,145,'06/10/2026'),(201,145,'CON@TOR'),(265,145,'Connecticut Sun'),(426,145,'Example, Player'),(587,145,'Out'),(667,145,'Not'),(686,145,'With'),(708,145,'Team')])
        with patch('wnba_official_reports.PdfReader',return_value=type('Reader',(),{'pages':[page]})()):r=parse_report(b'pdf','official.pdf')
        self.assertEqual(r['records'][0]['team_code'],'CON')
        self.assertEqual(r['records'][0]['reported_reason'],'Not With Team')
    def test_concussion_continuation_does_not_create_an_extra_record(self):
        page=Page([(24,145,'06/10/2026'),(201,145,'CON@TOR'),(265,145,'Connecticut Sun'),(426,145,'Example, Player'),(587,145,'Out'),(667,138,'Injury/Illness - Right Head;'),(667,152,'Concussion Protocol')])
        with patch('wnba_official_reports.PdfReader',return_value=type('Reader',(),{'pages':[page]})()):r=parse_report(b'pdf','official.pdf')
        self.assertEqual(len(r['records']),1);self.assertEqual(r['records'][0]['reported_reason'],'Injury/Illness - Right Head; Concussion Protocol')
    def test_connecticut_alias_cannot_produce_false_zero(self):
        record=dict(game_date='2026-06-10',matchup='CON@TOR',team_code='CON',category='injury')
        report=dict(report_at='2026-06-10T17:00:00-04:00',matchups=[('2026-06-10','CON@TOR')],not_submitted=[],records=[record])
        with patch('wnba_official_reports.fetch_report',return_value=report):r=official_for_game('2026-06-10T23:00Z','CONN','CON@TOR')
        self.assertEqual(r['status'],'available');self.assertEqual(len(r['records']),1)
    def test_unknown_team_is_unavailable(self):
        with patch('wnba_official_reports.fetch_report') as f:r=official_for_game('2026-06-10T23:00Z','WRONG','CON@TOR')
        self.assertEqual(r['status'],'unavailable');f.assert_not_called()
    def test_official_records_survive_boxscore_failure(self):
        from requests import HTTPError
        comp=self.summary()['header']['competitions'][0]
        comp.update(status={'type':{'completed':True}})
        for side,tid in zip(comp['competitors'],['18','131935']):side['team']['id']=tid
        schedule=dict(team=dict(id='18',abbreviation='CON',displayName='Connecticut Sun'),events=[dict(id='123456',date=comp['date'],season={'year':2026},seasonType={'type':2},competitions=[comp])])
        with patch('collector.fetch',side_effect=[schedule,HTTPError('box score unavailable')]),patch('collector.time.sleep'),patch('wnba_official_reports.official_for_game',return_value=self.report()):r=collect('18',2026,2,5)
        self.assertEqual(len(r['games']),1);g=r['games'][0]
        self.assertEqual(g['box_score_status'],'unavailable');self.assertIsNone(g['entered']);self.assertEqual(g['players'],[])
        self.assertEqual(g['official_report_counts']['injury'],2);self.assertEqual(r['boxscore_loaded_games'],0)
        self.assertTrue(all(p['actual_participation']=='box_score_unavailable' for p in g['official_report']['records']))
    def test_repeated_umbrella_is_a_continuation_not_an_extra_player(self):
        page=Page([(24,145,'06/10/2026'),(201,145,'CON@TOR'),(265,145,'Connecticut Sun'),(426,145,'Parker- Tyus, Cheyenne'),(587,145,'Out'),(667,138,'Injury/Illness - Face Injury;'),(667,152,'Injury/Illness')])
        with patch('wnba_official_reports.PdfReader',return_value=type('Reader',(),{'pages':[page]})()):r=parse_report(b'pdf','official.pdf')
        self.assertEqual(len(r['records']),1);self.assertEqual(r['records'][0]['player_full_name'],'Cheyenne Parker-Tyus')
        self.assertEqual(r['records'][0]['reported_reason'],'Injury/Illness - Face Injury; Injury/Illness')
        self.assertEqual(r['records'][0]['category'],'injury')
    def test_foreign_unsubmitted_matchup_is_not_a_wnba_record(self):
        page=Page([(24,145,'06/10/2026'),(201,145,'CON@TOR'),(265,145,'Connecticut Sun'),(426,145,'Example, Player'),(587,145,'Out'),(667,145,'Injury/Illness - Left Ankle'),(201,175,'MEM@OKC'),(265,175,'Memphis Grizzlies'),(667,175,'NOT YET SUBMITTED')])
        with patch('wnba_official_reports.PdfReader',return_value=type('Reader',(),{'pages':[page]})()):r=parse_report(b'pdf','official.pdf')
        self.assertEqual(len(r['records']),1);self.assertNotIn(('2026-06-10','MEM@OKC'),r['matchups'])
    def test_wrong_source_game_does_not_supply_participation(self):
        comp=self.summary()['header']['competitions'][0];comp.update(status={'type':{'completed':True}})
        for side,tid in zip(comp['competitors'],['18','131935']):side['team']['id']=tid
        schedule=dict(team=dict(id='18',abbreviation='CON',displayName='Connecticut Sun'),events=[dict(id='123456',date=comp['date'],season={'year':2026},competitions=[comp])])
        wrong=self.summary();wrong['header']['id']='654321'
        with patch('collector.fetch',side_effect=[schedule,wrong]),patch('collector.time.sleep'),patch('wnba_official_reports.official_for_game',return_value=self.report()):r=collect('18',2026)
        self.assertEqual(r['boxscore_loaded_games'],0);self.assertEqual(r['games'][0]['players'],[])
        self.assertIn('different game',r['errors'][0]['message'])
    def test_nonobject_and_noninteger_api_payloads(self):
        client=app.test_client()
        for body in (None,[],['invalid'],{'limit':True},{'limit':5.5},{'season':2026.5}):
            self.assertEqual(client.post('/api/query',json=body).status_code,400)
if __name__=='__main__':unittest.main()
