import unittest
try:
    from sources.ucb_nyc import fetch_ucb_nyc
except ImportError:
    fetch_ucb_nyc = None


def page(total, ids):
    return f'<option value="nyc">NYC ({total})</option>' + ''.join(
        f'<article class="ucb-card"><h3 class="ucb-event-post-title"><a href="https://ucbcomedy.com/show/{i}/">Own show {i}</a></h3><div class="event-post-date">October 1, 2026 @ 7 PM</div><div class="ucb-event-post-location">NY Mainstage Livestream</div></article>' for i in ids) + ('' if ids else 'No items found matching your criteria.')


@unittest.skipIf(fetch_ucb_nyc is None, 'Deployment source not installed')
class UcbPagerTests(unittest.TestCase):
    def run_pages(self, pages):
        it=iter(pages)
        return fetch_ucb_nyc(fetch_text=lambda url: next(it))

    def test_complete_and_preserves_own_delivery(self):
        md,n=self.run_pages([page(3,[1,2]),page(3,[3]),page(3,[])])
        self.assertEqual(n,3)
        self.assertIn('NY Mainstage Livestream',md)
        self.assertIn('https://ucbcomedy.com/show/3/',md)

    def test_truncation_and_repeated_page_fail(self):
        for pages in ([page(3,[1,2]),page(3,[])],[page(3,[1,2]),page(3,[1,2])]):
            with self.assertRaises(ValueError): self.run_pages(pages)

    def test_changed_total_and_missing_terminal_fail(self):
        for pages in ([page(3,[1,2]),page(4,[3])],[page(2,[1,2]),'<option value="nyc">NYC (2)</option>']):
            with self.assertRaises(ValueError): self.run_pages(pages)
