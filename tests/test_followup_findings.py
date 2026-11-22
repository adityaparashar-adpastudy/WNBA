import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import requests
from collector import classify_dnp,dnp_counts,game_dates,fetch
from wnba_official_reports import clean_name,name_key,enrich_game,parse_report,official_for_game
import test_research_integrity as fixtures
Page=fixtures.Page

class ClassificationFollowupTests(unittest.TestCase):
    def test_anatomical_and_musculoskeletal_reason_families(self):
        for reason in ['LIGAMENTS','LIGAMENT TEAR','LEFT ABDUCTOR','RIGHT ADDUCTOR','ABDUCTORS','PECTORALIS','DELTOID','TENDONS','TENDINITIS','TENOSYNOVITIS','PLANTAR FASCIITIS','BURSITIS','LUMBAR SPASM','CERVICAL SPINE','HERNIATED DISC','GASTROCNEMIUS','ILIOPSOAS','LOWER BODY']:
            with self.subTest(reason=reason):self.assertEqual(classify_dnp(reason)['dnp_category'],'injury')
    def test_itis_is_not_blanket_injury(self):
        for reason in ['BRONCHITIS','MYOCARDITIS','APPENDICITIS']:
            r=classify_dnp(reason);self.assertEqual(r['dnp_category'],'unknown');self.assertTrue(r['health_dnp'])
        self.assertEqual(classify_dnp('ILLNESS - BRONCHITIS')['dnp_category'],'illness')
    def test_ambiguous_health_subgroup_stays_within_unknown(self):
        reasons=['Injury/Illness','HEALTH & SAFETY PROTOCOLS','Health and safety protocols','COLLAPSED LUNG','INJURY/ILLNESS - CYST','INJURY/ILLNESS - N/A; RECONDITIONING','INJURY/ILLNESS - INACTIVE']
        players=[dict(played=False,**classify_dnp(r)) for r in reasons]
        for p in players:self.assertEqual(p['dnp_category'],'unknown');self.assertTrue(p['health_dnp'])
        c=dnp_counts(players);self.assertEqual(c['unknown_dnp'],7);self.assertEqual(c['health_unspecified_dnp'],7);self.assertEqual(c['injury_dnp'],0)
    def test_management_requires_specific_medical_reason(self):
        for reason in ['LOAD MANAGEMENT','INJURY MANAGEMENT','REST - INJURY MANAGEMENT','N/A; REST']:
            self.assertEqual(classify_dnp(reason)['dnp_category'],'other')
        self.assertEqual(classify_dnp('REST - LEFT KNEE INJURY MANAGEMENT')['dnp_category'],'injury')
        self.assertEqual(classify_dnp('LOAD MANAGEMENT - ILLNESS')['dnp_category'],'illness')

class ReportFollowupTests(unittest.TestCase):
    def test_all_name_fields_remove_pdf_hyphen_space_but_keep_raw(self):
        for source in ['Laney- Hamilton','Littlepage- Buggs','Nelson- Ododa','Parker- Tyus','Hines- Allen']:
            page=Page([(24,145,'06/10/2026'),(201,145,'CON@TOR'),(265,145,'Connecticut Sun'),(426,145,source+', Player'),(587,145,'Out'),(667,145,'Injury/Illness - Left Knee')])
            with patch('wnba_official_reports.PdfReader',return_value=Mock(pages=[page])):record=parse_report(b'pdf','source')['records'][0]
            self.assertNotIn('- ',record['source_player_name']);self.assertIn('- ',record['source_player_name_raw']);self.assertNotIn('- ',record['player_full_name'])
        self.assertEqual(clean_name('Hines – Allen'),'Hines-Allen');self.assertEqual(clean_name('Paopao'),'Paopao');self.assertEqual(clean_name('Paopao, Te- Hina'),'Paopao, Te-Hina')
    def test_out_and_played_are_preserved_and_flagged(self):
        fixture=fixtures.IntegrityTests();r=fixture.report();r['records'][0]['reported_status']='Out';s=fixture.summary()
        from collector import parse_players
        with patch('wnba_official_reports.official_for_game',return_value=r):g=enrich_game(dict(players=parse_players(s,'18')),s,{},dict(abbreviation='CONN'))
        x=g['official_report']['records'][0];self.assertEqual(x['reported_status'],'Out');self.assertEqual(x['actual_participation'],'played');self.assertTrue(x['report_participation_discrepancy']);self.assertEqual(g['official_out_played'],1)
        self.assertEqual(g['official_report']['records'][1]['unmatched_reason'],'no_exact_source_name')
    def test_source_full_name_variant_can_join_without_fuzzy_matching(self):
        fixture=fixtures.IntegrityTests();r=fixture.report();r['records']=r['records'][:1];r['records'][0]['player_full_name']='Full Source Name'
        players=[dict(name='Display Name',source_names=['Full Source Name'],id='123',played=True,participation_status='played',reported_minutes='2')]
        with patch('wnba_official_reports.official_for_game',return_value=r):g=enrich_game(dict(players=players),fixture.summary(),{},dict(abbreviation='CONN'))
        self.assertEqual(g['official_report']['records'][0]['join_method'],'exact_source_name_variant')
        self.assertEqual(name_key('Betnijah Laney- Hamilton'),name_key('Betnijah Laney-Hamilton'))
    def test_hartford_game_date_matches_eastern_snapshot_date(self):
        d=game_dates({'gameInfo':{'venue':{'address':{'city':'Hartford','state':'CT'}}}}, {'date':'2026-07-03T00:00Z'})
        self.assertEqual(d['date'],'2026-07-02');self.assertEqual(d['date_utc'],'2026-07-03');self.assertEqual(d['date_timezone'],'America/New_York')
    def test_404_is_not_cached_and_refresh_retries_source(self):
        bad=Mock();bad.raise_for_status.side_effect=requests.HTTPError('404')
        ok=Mock();ok.raise_for_status.return_value=None;ok.json.return_value={'boxscore':{'players':[{}]}}
        with tempfile.TemporaryDirectory() as tmp,patch('collector.CACHE',Path(tmp)),patch('collector.requests.get',side_effect=[bad,ok]) as get:
            with self.assertRaises(requests.HTTPError):fetch('/summary',{'event':'missing'},True)
            self.assertEqual(list(Path(tmp).glob('*.json')),[])
            result=fetch('/summary',{'event':'missing'},True);self.assertTrue(result['boxscore']['players']);self.assertEqual(get.call_count,2)
