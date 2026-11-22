"""Regression cases from the 2025 live-data audit, plus timezone edge cases."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collector import classify_dnp, dnp_counts, game_dates, parse_players

class DnpCategoryTests(unittest.TestCase):
    def test_audited_health_reasons(self):
        # Source language, not clinical inference: mixed/unspecified health stays unknown.
        expected={'ILLNESS':'illness','INJURY/ILLNESS - LEFT KNEE':'injury','RIGHT HEAD':'injury','LEFT THUMB':'injury','RIGHT LEG':'injury',
                  'RIGHT LOWER LEG':'injury','LOWER LEG':'injury','LEFT QUAD':'injury',
                  'LEFT HIP DISCOMFORT':'injury','LEFT PINKY; DISLOCATION':'injury','LEFT ADDUCTOR; TIGHTNESS':'injury','LEFT THIGH; NA':'injury','LEFT ARM; ARM':'injury','COLLAPSED LUNG':'unknown',
                  'INJURY/ILLNESS':'unknown','RETURN TO COMPETITION RECONDITIONING':'unknown'}
        for reason,category in expected.items():
            with self.subTest(reason=reason):
                actual=classify_dnp(reason)
                self.assertEqual(actual['dnp_category'],category)
                self.assertTrue(actual['health_dnp'])
    def test_unknown_and_non_injury_reasons(self):
        for reason in ["COACH'S DECISION",'NOT WITH TEAM','NOT WITH TEAM - PREGNANCY',
                       "COACH'S DECISION - DEVELOPMENTAL PLAYER","COACH'S DECISION - COACH ’ S DECISION",'LEAGUE SUSPENSION','REST - N/A','N/A; REST','PERSONAL REASONS','REST','NOT INJURY RELATED','NON-INJURY RELATED']:
            with self.subTest(reason=reason):
                result=classify_dnp(reason)
                self.assertEqual(result['dnp_category'],'other')
                self.assertFalse(result['health_dnp'])
        for reason in ['',None,'UNRECOGNIZED REASON','EYEWITNESS','DID NOT DRESS','DID NOT PLAY','INACTIVE']:
            self.assertEqual(classify_dnp(reason)['dnp_category'],'unknown')
    def test_reason_normalization(self):
        self.assertEqual(classify_dnp(' DNP - left   thumb ')['dnp_category'],'injury')
        self.assertEqual(classify_dnp('coach’s decision')['dnp_category'],'other')
    def test_counts_are_exclusive_and_cover_every_dnp(self):
        players=[dict(played=False,**classify_dnp(reason)) for reason in
                 ['LEFT THUMB','ILLNESS',"COACH'S DECISION",'', 'INJURY/ILLNESS']]
        players.append(dict(played=True,dnp_category=None,health_dnp=False))
        counts=dnp_counts(players)
        self.assertEqual(counts,dict(injury_dnp=1,illness_dnp=1,other_dnp=1,unknown_dnp=2,health_unspecified_dnp=1))
        self.assertEqual(sum(counts[k] for k in ['injury_dnp','illness_dnp','other_dnp','unknown_dnp']),5)
    def test_player_reason_preserved_and_participant_not_classified(self):
        athletes=[{'athlete':{'id':'1','displayName':'Player'},'didNotPlay':True,'reason':'LEFT THUMB','stats':[]},
                  {'athlete':{'id':'2','displayName':'Entered'},'reason':'INJURY/ILLNESS','stats':['12']}]
        summary={'boxscore':{'players':[{'team':{'id':'5'},'statistics':[{'labels':['MIN'],'athletes':athletes}]}]}}
        rows=parse_players(summary,'5')
        self.assertEqual(rows[0]['reason'],'LEFT THUMB')
        self.assertTrue(rows[0]['injury_dnp'])
        self.assertEqual(rows[0]['dnp_category'],'injury')
        self.assertIsNone(rows[1]['dnp_category'])
        self.assertFalse(rows[1]['injury_dnp'])

class GameDateTests(unittest.TestCase):
    def dates(self,stamp,city,state):
        return game_dates({'gameInfo':{'venue':{'address':{'city':city,'state':state}}}},
                          {'date':stamp,'competitions':[{'competitors':[{'team':{'displayName':'Chicago Sky'}}]}]})
    def test_official_golden_state_opener_local_date(self):
        actual=self.dates('2025-05-17T02:00Z','San Francisco','CA')
        self.assertEqual(actual['date'],'2025-05-16')
        self.assertEqual(actual['date_utc'],'2025-05-17')
        self.assertEqual(actual['date_timezone'],'America/Los_Angeles')
        self.assertEqual(actual['date_basis'],'venue_local')
        self.assertEqual(actual['start_time_utc'],'2025-05-17T02:00:00Z')
    def test_neutral_site_and_secondary_venues(self):
        self.assertEqual(self.dates('2025-08-16T06:00Z','Vancouver','BC')['date'],'2025-08-15')
        for city,state in [('Baltimore','MD'),('Fairfax','VA')]:
            self.assertEqual(self.dates('2025-06-02T01:00Z',city,state)['date'],'2025-06-01')
    def test_dst_and_phoenix(self):
        self.assertEqual(self.dates('2025-01-10T07:30Z','Los Angeles','CA')['date'],'2025-01-09')
        self.assertEqual(self.dates('2025-03-10T07:30Z','Los Angeles','CA')['date'],'2025-03-10')
        self.assertEqual(self.dates('2025-01-10T07:30Z','Phoenix','AZ')['date'],'2025-01-10')
    def test_unknown_venue_does_not_guess(self):
        actual=self.dates('2025-05-17T02:00Z','Unknown City','XX')
        self.assertEqual(actual['date'],'2025-05-17')
        self.assertEqual(actual['date_basis'],'utc_fallback')
        self.assertEqual(actual['date_timezone'],'UTC')
    def test_date_without_timezone_is_explicit(self):
        actual=self.dates('2025-05-17','San Francisco','CA')
        self.assertEqual(actual['date'],'2025-05-17')
        self.assertEqual(actual['date_basis'],'source_date')
        self.assertIsNone(actual['start_time_utc'])
if __name__=='__main__':unittest.main()
