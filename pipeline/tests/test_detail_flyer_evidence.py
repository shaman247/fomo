"""Title-only records must not borrow a genre from their venue (2026-10-09).

Parkside Lounge's "SomethingTogether" listing gave only a title and a date; its
detail page's only content is a flyer announcing a poetry reading and book
launch. The extractor tagged it Music/Concert 🎶 from the venue's description.
"""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extractor
from merger import compute_voted_tags


PAGE = 'https://www.parksidelounge.nyc/calendar/somethingtogether'
SQS = ('https://images.squarespace-cdn.com/content/v1/624d/80f9/'
       'something+together+launch+flier.jpg')


class SelectDetailImagesTests(unittest.TestCase):
    def test_keeps_flyer_and_drops_chrome(self):
        content = '\n'.join([
            '![](https://cdn.userway.org/widgetapp/images/spin_wh.svg)',
            '![](https://example.org/wp-content/plugins/the-events-calendar/images/tribe-loading.gif)',
            f'# SomethingTogether\n![]({SQS})',
            f'![]({SQS}?format=500w)',
            '![](https://mapsapi.tmol.io/maps/geometry/3/event/1/image?systemId=HOST)',
            '![](https://tpc.googlesyndication.com/simgad/118947)',
            '![](https://www.google.com/maps/vt?pb=!1m5)',
            '![](https://secure.meetupstatic.com/next/images/fallbacks/redesign/event-cover-4.webp)',
            f'![]({PAGE})',
        ])
        self.assertEqual(extractor.select_detail_images(content, PAGE), [SQS])

    def test_wordpress_and_wix_renditions_are_one_image(self):
        content = ('![](https://copo.org/wp-content/uploads/2025/03/Movie-Morning.jpg)\n'
                   '![](https://copo.org/wp-content/uploads/2025/03/Movie-Morning-232x300.jpg)\n'
                   '![](https://static.wixstatic.com/media/a~mv2.jpg/v1/fill/w_675,h_844/a.jpg)\n'
                   '![](https://static.wixstatic.com/media/a~mv2.jpg/v1/fill/w_147,h_184/a.jpg)')
        self.assertEqual(extractor.select_detail_images(content, 'https://copo.org/event/x/'), [
            'https://copo.org/wp-content/uploads/2025/03/Movie-Morning.jpg',
            'https://static.wixstatic.com/media/a~mv2.jpg/v1/fill/w_675,h_844/a.jpg'])

    def test_cloudinary_renditions_and_map_spacers(self):
        art = 'https://assets.shotgun.live/image/upload/{}/production/artworks/poster_x.jpg'
        content = '\n'.join([
            '![](https://maps.gstatic.com/mapfiles/transparent.png)',
            '![](' + art.format('c_limit,w_384/fl_lossy/f_auto/q_5') + ')',
            '![](' + art.format('c_limit,ar_16:9,w_3840/fl_lossy/f_auto/q_auto/v1785516046') + ')',
        ])
        self.assertEqual(extractor.select_detail_images(content, 'https://nublu.net/e/1'),
                         [art.format('c_limit,ar_16:9,w_3840/fl_lossy/f_auto/q_auto/v1785516046')])

    def test_capped_in_page_order(self):
        content = '\n'.join(f'![](https://example.org/uploads/flyer-{n}.jpg)' for n in range(6))
        selected = extractor.select_detail_images(content, 'https://example.org/e/1')
        self.assertEqual(selected, [f'https://example.org/uploads/flyer-{n}.jpg'
                                    for n in range(extractor.DETAIL_IMAGE_LIMIT)])


class DetailFlyerPacketTests(unittest.TestCase):
    def run_detail(self, images):
        captured = {}

        async def fake_generate(prompt, schema, timeout=None, **kwargs):
            captured.update(prompt=prompt, **kwargs)
            return json.dumps({'description': 'A poetry reading and book launch.',
                               'hashtags': ['Literature', 'Poetry', 'BookLaunch'],
                               'emoji': '📖', 'location': 'Parkside Lounge'})

        with patch.object(extractor.llm_providers, 'is_configured', return_value=True), \
                patch.object(extractor.llm_providers, 'generate_structured', fake_generate), \
                patch.object(extractor, '_prompt_rule', side_effect=lambda name: getattr(extractor, name)), \
                patch.object(extractor.agent_extraction, 'reference_date', return_value='2026-10-09'):
            result = asyncio.run(extractor.extract_single_event(
                'SomethingTogether', 'SomethingTogether\nSunday, October 11', url=PAGE, images=images))
        return captured, result

    def test_images_ride_in_the_packet_with_reading_instructions(self):
        image = {'inline_data': {'mime_type': 'image/jpeg', 'data': 'AAAA'}}
        captured, result = self.run_detail([image])
        self.assertEqual(captured['images'], [image])
        self.assertIn('content images are attached (1, in page order)', captured['prompt'])
        self.assertEqual(result['description'], 'A poetry reading and book launch.')

    def test_text_pass_carries_no_image_note(self):
        captured, _ = self.run_detail(None)
        self.assertIsNone(captured['images'])
        self.assertNotIn('content images are attached', captured['prompt'])


class TagEvidenceRuleTests(unittest.TestCase):
    def test_prompts_no_longer_force_a_category(self):
        for name in ('VISION_INSTRUCTIONS_TEMPLATE', 'ENRICHMENT_PROMPT_TEMPLATE', 'SINGLE_PROMPT_TEMPLATE'):
            text = getattr(extractor, name)
            self.assertNotIn('Always include at least one category', text, name)
            self.assertIn('NOT evidence about this event', text, name)
        for model in (extractor.Event, extractor.EventEnrichment, extractor.SingleEventExtraction):
            self.assertIn('return [] rather than guess', model.model_fields['hashtags'].description)


class FakeVoteCursor:
    """Answers compute_voted_tags' queries from (tags, described) source rows."""

    def __init__(self, sources):
        self.sources = sources
        self.result = None

    def execute(self, sql, params=()):
        described_only = 'ce.description NOT IN' in sql
        rows = [(tags, d) for tags, d in self.sources if d or not described_only]
        if 'SELECT EXISTS' in sql:
            self.result = [(int(any(d for _, d in self.sources)),)]
        elif 'GROUP BY cet.tag' in sql:
            counts = {}
            for tags, _ in rows:
                for tag in set(tags):
                    counts[tag] = counts.get(tag, 0) + 1
            self.result = list(counts.items())
        else:
            self.result = [(len(rows),)]

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0]


class EvidenceWeightedVoteTests(unittest.TestCase):
    CURATED = {'Music', 'Concert', 'Literature', 'Poetry'}
    GUESSES = [(['Music', 'Concert'], False)] * 5

    def vote(self, sources, current, current_described):
        return set(compute_voted_tags(FakeVoteCursor(sources), 1, current, self.CURATED,
                                      {}, {'music', 'literature'},
                                      current_described=current_described))

    def test_described_source_outvotes_repeated_title_guesses(self):
        tags = self.vote(self.GUESSES, ['Literature', 'Poetry'], True)
        self.assertEqual(tags, {'Literature', 'Poetry'})

    def test_later_title_only_crawl_cannot_revive_the_guess(self):
        sources = self.GUESSES + [(['Literature', 'Poetry'], True)]
        self.assertEqual(self.vote(sources, ['Music', 'Concert'], False), {'Literature', 'Poetry'})

    def test_title_only_history_follows_the_newest_crawl(self):
        self.assertEqual(self.vote(self.GUESSES, ['Music', 'Concert'], False), {'Music', 'Concert'})
        self.assertEqual(self.vote(self.GUESSES, ['Literature'], False), {'Literature'})

    def test_pre_fix_title_guesses_cannot_outvote_a_newer_blank(self):
        # E282893 "Drive in Saturdays": three pre-2026-10-09 title-only crawls
        # guessed Concert; the post-fix crawl says ["Other"] (or nothing).
        sources = [(['Music', 'Concert'], False)] * 3
        self.assertEqual(self.vote(sources, ['Other'], False), {'Other'})
        self.assertEqual(self.vote(sources, [], False), {'Other'})

    def test_described_sources_still_vote_among_themselves(self):
        sources = [(['Literature', 'Poetry'], True)] * 3 + [(['Literature', 'Music'], True)]
        self.assertEqual(self.vote(sources, ['Literature', 'Poetry'], True), {'Literature', 'Poetry'})


if __name__ == '__main__':
    unittest.main()
