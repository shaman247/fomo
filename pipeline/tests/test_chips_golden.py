"""Explicit Golden slots, completeness gates, and public metadata boundaries."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from sources import chips_golden as golden
except ImportError:
    golden = None


@unittest.skipIf(golden is None, 'Deployment source plugin unavailable')
class GoldenTests(unittest.TestCase):
    def setUp(self):
        self.card = {'id': 'abc123', 'organizationId': 'org1', 'name': 'Food Rescue',
                     'status': 'active', 'additionalTimes': 1}
        self.detail = {'id': 'abc123', 'organizationId': 'org1', 'title': 'Food Rescue',
            'organizationName': 'CHiPS', 'visibilitySetting': 'public',
            'accessibilitySetting': 'open', 'timezoneId': 'America/New_York',
            'fullDescription': 'Bring surplus food to the community kitchen.',
            'purpose': 'Reduce food waste.', 'role': 'Collect food.', 'vibe': 'Hands on.',
            'city': 'Brooklyn', 'state': 'NY', 'zip': '11215',
            'streetAddress': 'PRIVATE_PICKUP', 'proTips': 'SIGNUP_ONLY_INFORMATION',
            'times': [self.slot('a', '2026-10-30T21:45:00Z', '2026-10-30T22:45:00Z'),
                      self.slot('b', '2026-11-02T22:45:00Z', '2026-11-02T23:45:00Z', False)]}

    def slot(self, key, start, end, available=True):
        return {'id': key, 'start': start, 'end': end, 'available': available,
                'isVisibleInPortal': True, 'timeType': 'setTime',
                'startTime': '2026-01-01T01:00:00Z'}

    def render(self):
        return golden.opportunity_markdown(self.card, self.detail, 'org1')

    def test_actual_instants_preserve_dst_and_full_slots(self):
        text = self.render()
        self.assertIn('2026-10-30 17:45 EDT', text)
        self.assertIn('2026-11-02 17:45 EST', text)
        self.assertEqual(text.count('\n- '), 2)
        self.assertIn('Full / waitlist', text)
        self.assertNotIn('PRIVATE_PICKUP', text)
        self.assertNotIn('SIGNUP_ONLY_INFORMATION', text)
        self.assertNotIn('2026-01-01', text)

    def test_distinct_weekend_clock_and_overnight_date(self):
        self.detail['times'][1] = self.slot('b', '2026-10-31T16:15:00Z', '2026-10-31T17:15:00Z')
        self.assertIn('2026-10-31 12:15 EDT', self.render())
        self.detail['times'][1] = self.slot('b', '2026-11-01T03:30:00Z', '2026-11-01T05:00:00Z')
        self.assertIn('2026-10-31 23:30 EDT to 2026-11-01 01:00 EDT', self.render())

    def test_count_cannot_manufacture_dates(self):
        for count in (29, -1, True, None):
            self.card['additionalTimes'] = count
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.render()

    def test_unknown_or_incomplete_schedules_fail_closed(self):
        for changes in ({'start': '2026-10-30T17:45:00'}, {'end': '2026-10-29T21:45:00Z'},
                        {'timeType': 'anyTime'}, {'isVisibleInPortal': None}, {'available': None}):
            detail = copy.deepcopy(self.detail)
            detail['times'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                golden.explicit_slots(detail)
        self.detail['times'].append(self.detail['times'][0].copy())
        with self.assertRaises(ValueError):
            golden.explicit_slots(self.detail)

    def test_cancelled_and_private_slots_are_not_emitted(self):
        self.detail['times'] += [dict(self.detail['times'][0], id='c', isCancelled=True),
                                 dict(self.detail['times'][0], id='d', isVisibleInPortal=False)]
        self.assertEqual(self.render().count('\n- '), 2)

    def test_wrong_identity_and_private_opportunities_fail_closed(self):
        for key, value in [('id', 'other'), ('organizationId', 'foreign'),
                           ('visibilitySetting', 'private'), ('accessibilitySetting', 'restricted'),
                           ('title', 'Different opportunity')]:
            detail = dict(self.detail, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                golden.opportunity_markdown(self.card, detail, 'org1')

    def session(self, batches):
        config = {'props': {'domain': golden.HOST, 'isPublic': True,
                  'configuration': {'apiKey': 'public-test-key', 'organizationId': 'org1'}}}
        page = Mock(text='<script id="__NEXT_DATA__">' + json.dumps(config) + '</script>')
        responses = [page, *[Mock(json=Mock(return_value=b)) for b in batches],
                     Mock(json=Mock(return_value=self.detail))]
        session = Mock(headers={})
        session.get.side_effect = responses
        return session

    def test_fetch_uses_public_bootstrap_and_expands_detail(self):
        session = self.session([[self.card]])
        text, count = golden.fetch_and_build_markdown([golden.ORIGIN], session=session)
        self.assertEqual(count, 1)
        self.assertEqual(text.count('\n- '), 2)
        self.assertNotIn('public-test-key', text)
        detail_call = session.get.call_args
        self.assertTrue(detail_call.args[0].endswith('/abc123'))
        self.assertEqual(detail_call.kwargs['params']['includeWaitlisted'], 'true')

    def test_paginated_listing_must_terminate_and_not_repeat(self):
        batch = [dict(self.card, id=f'id{i}') for i in range(25)]
        with self.assertRaises(ValueError):
            golden.fetch_and_build_markdown([golden.ORIGIN], session=self.session([batch]), max_pages=1)
        with self.assertRaises(ValueError):
            golden.fetch_and_build_markdown([golden.ORIGIN], session=self.session([batch, batch]))

    def test_wrong_source_rejected_before_requests(self):
        for url in ('https://elsewhere.test/', golden.ORIGIN + '/opportunities/abc123'):
            session = Mock()
            with self.assertRaises(ValueError):
                golden.fetch_and_build_markdown([url], session=session)
            session.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
