"""Session identity comes from dated destinations or attributed event schedules."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from detail_identity import detail_rejection_reason as reject, url_session_dates

OLD = 'https://example.test/old-2026-09-18'
NEW = 'https://other.test/new-path-2026-10-03'
URL = 'https://example.test/reused'
SESSION = {'name': 'Contra Connections', 'occurrences': [{'start_date': '2026-10-04'}]}


def result(final=URL, event=None, **kwargs):
    html = '' if event is None else '<script type="application/ld+json">' + json.dumps(event) + '</script>'
    return SimpleNamespace(redirected_url=final, html=html, **kwargs)


def event(start, **kwargs):
    return {'@type': 'Event', 'url': URL, 'name': 'Contra Connections', 'startDate': start, **kwargs}


class DetailIdentityEvidenceTests(unittest.TestCase):
    def test_changed_paths_and_hosts_still_cannot_change_date(self):
        self.assertIsNotNone(reject(OLD, result(NEW)))

    def test_named_query_date_is_explicit_evidence(self):
        self.assertIsNotNone(reject(URL + '?date=2026-09-18', result(URL + '?date=2026-10-03')))
        self.assertEqual(url_session_dates(URL + '?tracking=2026-10-03'), set())
        self.assertEqual(url_session_dates(URL + '?date=10/03/26'), set())

    def test_reused_undated_url_cannot_import_later_session(self):
        self.assertIsNotNone(reject(URL, result(event=event('2026-12-05T14:00:00-05:00')), SESSION))

    def test_missing_final_url_still_checks_structured_event_evidence(self):
        self.assertIsNotNone(reject(URL, result(None, event('2026-12-05')), SESSION))
        self.assertIsNotNone(reject(OLD, result(None, url=NEW)))

    def test_missing_metadata_alone_is_not_a_contradiction(self):
        self.assertIsNone(reject(OLD, result(None)))
        self.assertIsNone(reject(URL, result(None), SESSION))

    def test_same_session_canonical_redirect_and_local_timezone_survive(self):
        self.assertIsNone(reject(URL, result(event=event('2026-10-04T23:30:00-04:00')), SESSION))
        self.assertIsNone(reject(OLD, result('https://other.test/2026/09/18/revised')))

    def test_multiple_sessions_and_ranges_preserve_overlap(self):
        self.assertIsNone(reject(URL, result(event=[event('2026-12-05'), event('2026-10-04')]), SESSION))
        self.assertIsNone(reject(URL, result(event=event('2026-10-01', endDate='2026-10-06')), SESSION))
        grouped = dict(SESSION, occurrences=SESSION['occurrences'] + [{'start_date': '2026-12-05'}])
        self.assertIsNone(reject(URL, result(event=event('2026-12-05')), grouped))

    def test_unattributed_recommendation_does_not_veto(self):
        self.assertIsNone(reject(URL, result(event=event('2026-12-05', url='https://other.test/event', name='Other')), SESSION))
        self.assertIsNone(reject(URL, result(event={'@type':'WebPage', 'relatedLink':event('2026-12-05')}), SESSION))

    def test_graph_name_identity_and_invalid_dates(self):
        self.assertIsNotNone(reject(URL, result(event={'@graph':[event('2026-12-05', url=None)]}), SESSION))
        self.assertIsNone(reject(URL, result(event=event('2026-02-30')), SESSION))
        self.assertIsNone(reject(URL, result(event=event('2026-12-05', endDate='2026-10-01')), SESSION))

    def test_declared_website_branding_is_not_part_of_session_title(self):
        branded = event('2026-12-05', url=None, name='Contra Connections — Brooklyn Contra')
        payload = [{'@type':'WebSite','name':'Brooklyn Contra'},branded]
        self.assertIsNotNone(reject(URL,result(event=payload),SESSION))
        self.assertIsNone(reject(URL,result(event=branded),SESSION))

    def test_requested_date_checks_event_html_even_without_saved_schedule(self):
        self.assertIsNotNone(reject(OLD, result(None, event('2026-10-03', url=OLD))))

    def test_stable_first_date_url_keeps_later_recurring_sessions(self):
        url = 'https://gallery.test/exhibitions/2026/9/12/artichoke'
        expected = {'name':'Artichoke','occurrences':[{'start_date':'2026-10-03'}]}
        self.assertIsNone(reject(url,result(url),expected))
        self.assertIsNone(reject(url,result(url,event('2026-09-12',
            endDate='2026-10-03',url=url,name='Artichoke')),expected))

    def test_attributed_series_interval_wins_over_first_date_destination(self):
        url = 'https://gallery.test/exhibitions/2026/9/12/artichoke'
        expected = {'name':'Artichoke','occurrences':[{'start_date':'2026-10-03'}]}
        self.assertIsNone(reject(URL,result(url,event('2026-09-12',
            endDate='2026-10-03',url=url,name='Artichoke')),expected))
        self.assertIsNotNone(reject(URL,result(url),expected))

    def test_explicit_date_redirect_still_vetoes_even_if_series_overlaps(self):
        self.assertIsNotNone(reject(OLD,result(NEW,event('2026-09-01',
            endDate='2026-10-30',url=NEW)),{'start_date':'2026-10-03'}))

    def test_source_objects_and_url_are_never_mutated(self):
        before=json.dumps(SESSION,sort_keys=True)
        reject(URL,result(event=event('2026-12-05')),SESSION)
        self.assertEqual(before,json.dumps(SESSION,sort_keys=True))


if __name__ == '__main__':
    unittest.main()
