"""Deployment-level coverage checks for the reviewed library window rollout."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import site_profiles
try:
    from sources import librarycalendar_pager as plugin
except ImportError:
    plugin = None


@unittest.skipIf(plugin is None, 'deployment-specific source plugin not installed')
class LibraryWindowTests(unittest.TestCase):
    hosts = ('ossining.librarycalendar.com', 'syosset.librarycalendar.com')

    def page(self, day, suffix, next_page=None, offsite=False):
        label = day.strftime('%A, %B %d, %Y')
        return (f'<article class="event-card node--type-lc-event">'
                f'<a class="lc-event__link" href="/event/{suffix}" '
                f'aria-label="Workshop on {label} @ 3pm">Workshop</a>'
                '<div class="lc-event__month-details"></div>'
                '<div class="lc-event__date">3pm–4pm</div>'
                f'<div class="lc-event__branch">{"Off Site" if offsite else "Library"}</div>'
                '</article>' + (f'<li class="pager__item--next"><a href="?page={next_page}">Next</a></li>'
                                if next_page is not None else ''))

    def run_pages(self, host, pages):
        responses = [Mock(content=p.encode(), text=p) for p in pages]
        session = Mock()
        session.headers = {}
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.side_effect = responses
        with patch.object(plugin.requests, 'Session', return_value=session), patch.object(
                plugin, 'get_active_date_window', return_value=(date(2026, 10, 1), date(2026, 12, 30))):
            result = plugin.fetch_and_build_markdown([
                f'https://{host}/events/upcoming?page=2',
                f'https://{host}/events/upcoming?page=3'])
        return result, session

    def test_dispatch_restarts_at_first_page_and_reaches_boundary(self):
        for host in self.hosts:
            with self.subTest(host=host):
                url = f'https://{host}/events/upcoming?page=2'
                self.assertIs(site_profiles.custom_fetch_profile([url]), plugin.PROFILE)
                (body, count), session = self.run_pages(host, [
                    self.page(date(2026, 10, 1), 'first', 1),
                    self.page(date(2026, 12, 25), 'late', 2),
                    self.page(date(2027, 1, 1), 'future', 3)])
                self.assertEqual(count, 2)
                self.assertIn('/event/late', body)
                self.assertNotIn('/event/future', body)
                self.assertEqual([c.args[0] for c in session.get.call_args_list], [
                    f'https://{host}/events/upcoming',
                    f'https://{host}/events/upcoming?page=1',
                    f'https://{host}/events/upcoming?page=2'])

    def test_later_page_failure_never_returns_partial_inventory(self):
        for host in self.hosts:
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, 'cards missing'):
                self.run_pages(host, [self.page(date(2026, 10, 1), 'first', 1), '<body>Access denied</body>'])

    def test_offsite_details_preserve_actual_venue(self):
        detail = ('<article class="lc-event--full"><div class="lc-event-branch">Off Site</div>'
                  '<div class="lc-event-location-address">Hilltop Kitchen, 150 Main Street</div>'
                  '<section class="lc-event__content">Silent Book Club</section></article>')
        (body, count), session = self.run_pages(self.hosts[1], [
            self.page(date(2026, 12, 1), 'offsite', offsite=True), detail])
        self.assertEqual(count, 1)
        self.assertIn('Hilltop Kitchen, 150 Main Street', body)
        self.assertEqual(session.get.call_args_list[-1].args[0], f'https://{self.hosts[1]}/event/offsite')


if __name__ == '__main__':
    unittest.main()
