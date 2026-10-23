"""Fresh metadata must not erase editorial work or another session's details."""
import copy
import json
import sqlite3
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_metadata import (plan_source_metadata_refresh, refresh_source_metadata,
                             tag_keep_threshold, tag_vote_survives)


class MetadataPlanTests(unittest.TestCase):
    def setUp(self):
        self.event = dict(id=1, website_id=10, reviewed=0, suppressed=0,
                          location_id=5, location_name='Art School', sublocation=None,
                          description='An artist talk.')
        self.prior = dict(id=20, website_id=10, crawled_at='2026-09-19 10:00:00',
                          location_id=5, location_name='Art School', sublocation=None,
                          description='An artist talk.', raw_data='{}')
        self.incoming = dict(self.prior, id=21, crawled_at='2026-09-21 10:00:00',
                             sublocation='15th floor',
                             description='An artist talk with an RSVP required; enter on East 21st Street.')
        self.sources = [self.prior]
        self.slots = [dict(start_date='2026-10-01', start_time='6pm', end_date=None)]
        self.incoming_slots = copy.deepcopy(self.slots)

    def plan(self):
        return plan_source_metadata_refresh(self.event, self.incoming, self.sources,
                                            self.slots, self.incoming_slots, date(2026, 9, 21))

    def test_new_source_recovers_room_and_unreviewed_source_text(self):
        self.assertEqual(self.plan(), dict(sublocation='15th floor',
                                          description=self.incoming['description']))

    def test_reviewed_description_remains_while_missing_room_can_fill(self):
        self.event['reviewed'] = 1
        self.assertEqual(self.plan(), {'sublocation': '15th floor'})

    def test_manual_unreviewed_text_is_not_source_owned(self):
        self.event['description'] = 'Editorial text.'
        self.assertEqual(self.plan(), {'sublocation': '15th floor'})

    def test_another_publishers_text_or_shared_sources_are_preserved(self):
        for mutation in ['owner', 'source']:
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation == 'owner':
                    self.event['website_id'] = 99
                else:
                    self.sources.append(dict(self.prior, id=30, website_id=99))
                self.assertEqual(self.plan(), {})

    def test_suppressed_or_unknown_or_different_venues_cannot_refresh(self):
        for changes in [dict(suppressed=1), dict(location_id=None), dict(location_id=7)]:
            with self.subTest(changes=changes):
                self.setUp(); self.event.update(changes)
                self.assertEqual(self.plan(), {})

    def test_empty_and_venue_only_rooms_fill_but_specific_rooms_remain(self):
        for room in [None, '', 'Not specified', 'TBA', ' Art School ']:
            self.event['sublocation'] = room
            self.assertEqual(self.plan()['sublocation'], '15th floor')
        for room in ['Room 101', 'Main Hall', 'Varies by session; see description']:
            self.event['sublocation'] = room
            self.assertNotIn('sublocation', self.plan())

    def test_historical_conflicting_room_prevents_blank_room_backfill(self):
        self.prior['sublocation'] = '2nd floor'
        self.assertNotIn('sublocation', self.plan())
        self.prior['sublocation'] = '15TH FLOOR'
        self.assertIn('sublocation', self.plan())

    def test_stale_same_time_or_unknown_freshness_cannot_refresh(self):
        for timestamp in ['2026-09-18 10:00:00', '2026-09-19 10:00:00', None]:
            self.incoming['crawled_at'] = timestamp
            self.assertEqual(self.plan(), {})
        self.setUp(); self.prior['crawled_at'] = None
        self.assertEqual(self.plan(), {})

    def test_rolling_subset_cannot_describe_remaining_series(self):
        self.slots.append(dict(start_date='2026-10-08', start_time='6pm', end_date=None))
        self.assertEqual(self.plan(), {})
        self.incoming_slots.append(copy.deepcopy(self.slots[-1]))
        self.assertIn('description', self.plan())

    def test_past_sessions_do_not_prevent_current_details(self):
        self.slots.append(dict(start_date='2026-09-01', start_time='6pm', end_date=None))
        self.assertIn('description', self.plan())

    def test_midnight_and_unknown_time_are_not_equivalent(self):
        self.slots[0]['start_time'] = '12am'
        self.incoming_slots[0]['start_time'] = ''
        self.assertEqual(self.plan(), {})
        self.incoming_slots[0]['start_time'] = '00:00'
        self.assertIn('description', self.plan())

    def test_distinct_spans_and_dateless_rows_cannot_refresh(self):
        self.slots[0]['end_date'] = '2026-11-01'
        self.assertEqual(self.plan(), {})
        self.slots = []; self.incoming_slots = []
        self.assertEqual(self.plan(), {})

    def test_incoming_grouped_details_keep_their_existing_policy(self):
        for raw in [json.dumps({'session_details': [{}, {}]}), 'bad JSON', '[]', '"text"']:
            self.incoming['raw_data'] = raw
            self.assertEqual(self.plan(), {})

    def test_ordinary_update_cannot_flatten_older_session_details(self):
        self.prior['raw_data'] = json.dumps({'session_details': [{}, {}]})
        self.assertNotIn('description', self.plan())

    def test_placeholder_or_absent_incoming_fields_cannot_erase_metadata(self):
        for description in [None, '', '  \n ', 'No description available.']:
            self.incoming.update(description=description, sublocation='Not specified')
            self.assertEqual(self.plan(), {})

    def test_price_only_extraction_cannot_replace_program_text_but_room_can_refresh(self):
        for description in ['Price: Free.', ' FREE ', 'Cost: $15.', 'Admission: $10–$20', 'Tickets: $12.50']:
            with self.subTest(description=description):
                self.incoming['description'] = description
                self.assertEqual(self.plan(), {'sublocation': '15th floor'})

    def test_real_short_or_price_bearing_description_can_refresh(self):
        for description in ['A printmaking survey.', 'Price: Free. An exhibition of mail art.',
                            'Free admission to a printmaking workshop.']:
            with self.subTest(description=description):
                self.incoming['description'] = description
                self.assertEqual(self.plan()['description'], description)

    def test_prior_price_only_text_can_recover_from_substantive_source(self):
        self.event['description'] = self.prior['description'] = 'Price: Free.'
        self.assertEqual(self.plan()['description'], self.incoming['description'])

    def test_listing_stub_cannot_abridge_detail_page_text(self):
        detail = ('Learn the basics of Tunisian crochet in three hours, including yarn and hook '
                  'information, how to begin a project, and the difference between regular and '
                  'Tunisian crochet. Students begin making a chunky headband; basic crochet skills required.')
        self.event['description'] = self.prior['description'] = detail
        for stub in ['Craft class at Brooklyn Craft Company. Price: $45.00.',
                     'A three-hour Tunisian crochet class for students with basic crochet skills.']:
            with self.subTest(stub=stub):
                self.incoming['description'] = stub
                self.assertEqual(self.plan(), {'sublocation': '15th floor'})

    def test_comparable_or_longer_rewrite_of_detail_text_still_refreshes(self):
        detail = 'A' * 120 + ' detail-page description of the class and its materials.'
        self.event['description'] = self.prior['description'] = detail
        for new in [detail[:-20] + ' updated; now in Studio 4.', detail + ' Registration now required.']:
            with self.subTest(new=new):
                self.incoming['description'] = new
                self.assertEqual(self.plan()['description'], new)

    def test_short_or_session_list_text_keeps_existing_refresh_policy(self):
        for old in ['An artist talk with a long-time member of the school.',
                    '2026-10-01 6pm\nNo description available.\n\n2026-10-01 6pm\n' + 'Doors 6pm. ' * 30]:
            with self.subTest(old=old[:20]):
                self.event['description'] = self.prior['description'] = old
                self.incoming['description'] = 'An artist talk; RSVP required.'
                self.assertEqual(self.plan()['description'], 'An artist talk; RSVP required.')

    def use_page_text(self, old, new, old_url='https://x.org/e/1', new_url='https://x.org/e/1/'):
        self.event['description'] = self.prior['description'] = old
        self.prior['url'], self.incoming['url'] = old_url, new_url
        self.incoming['description'] = new

    def test_same_page_paraphrase_keeps_stored_text_but_room_still_fills(self):
        # Re-extraction rewordings logged by the 2026-10 merges (BL21).
        for old, new in [
                ('Bowne House educators read stories celebrating December holidays and winter fun, '
                 'with a surprise craft and refreshments. For ages 5 and up with an adult; '
                 'admission by donation.',
                 'Bowne House educators read stories celebrating December holidays and winter fun, '
                 'with a surprise craft project and refreshments. For ages 5 and up, accompanied '
                 'by an adult. Donation in any amount.'),
                ('Speaking and listening exercises related to real-life situations to build English confidence.',
                 'Speaking and listening exercises related to real-life situations to help students '
                 'become more confident English speakers.'),
                ('Test your hearing by an Audiologist from Ear Works Audiology. Registration required.',
                 'Test your hearing by an Audiologist from Ear Works Audiology (Age Well Expo).'),
                ('A weekly game.\n2026-10-01 6pm', 'A weekly game.')]:
            with self.subTest(new=new[:30]):
                self.use_page_text(old, new)
                self.assertEqual(self.plan(), {'sublocation': '15th floor'})

    def test_real_description_change_on_the_same_page_still_refreshes(self):
        old = 'Teens sew a mushroom pocket pal or backpack charm.'
        for new in ['Teens sew a mushroom pocket pal or backpack charm. Registration required.',
                    '*SOLD OUT* Teens sew a mushroom pocket pal or backpack charm.',
                    'Teens sew a mushroom pocket pal or backpack charm, 4-6pm.',
                    'Teens sew a mushroom pocket pal or backpack charm. Free with RSVP.',
                    'A knitting circle for adults who want to finish winter scarves together.']:
            with self.subTest(new=new):
                self.use_page_text(old, new)
                self.assertEqual(self.plan()['description'], new)
        # Dropping a status marker may mean the event changed state again.
        self.use_page_text('Sold out. ' + old, old)
        self.assertEqual(self.plan()['description'], old)
        # Truncated stored text is replaced by the complete rewording.
        self.use_page_text('Teens sew a mushroom pocket pal or backpack...',
                           'Teens sew a mushroom pocket pal or a backpack charm.')
        self.assertIn('description', self.plan())

    def test_paraphrase_from_another_page_keeps_existing_policy(self):
        old = 'Speaking and listening exercises related to real-life situations to build English confidence.'
        new = ('Speaking and listening exercises related to real-life situations to help students '
               'become more confident English speakers.')
        self.use_page_text(old, new, new_url='https://x.org/calendar')
        self.assertEqual(self.plan()['description'], new)
        # Only the page that supplied the stored text counts as "the same page".
        self.sources.append(dict(self.prior, id=19, url='https://x.org/calendar',
                                 description='An older listing stub.'))
        self.assertEqual(self.plan()['description'], new)

    def test_linked_incoming_does_not_forge_prior_provenance(self):
        self.sources = [self.incoming]
        self.assertEqual(self.plan(), {})
        self.sources.append(self.prior)
        self.assertIn('description', self.plan())


class TagHysteresisTests(unittest.TestCase):
    def survives(self, tag, count, total, current=(), held=()):
        threshold = max(2, -(-total * 3 // 10))  # merger's add rule: max(2, ceil(30%))
        return tag_vote_survives(tag, count, threshold, total, set(current),
                                 None if held is None else set(held))

    def test_add_rule_is_unchanged_without_held_tags(self):
        self.assertTrue(self.survives('Live Music', 1, 6, current={'Live Music'}))
        self.assertTrue(self.survives('Jazz', 2, 6))
        self.assertFalse(self.survives('Jazz', 1, 6))
        self.assertFalse(self.survives('Jazz', 2, 10))
        self.assertTrue(self.survives('Jazz', 3, 10, held=None))

    def test_held_tag_stays_below_add_threshold_until_keep_share(self):
        # Live Music on 2 of 10 crawls: not enough to add, enough to keep.
        self.assertFalse(self.survives('Live Music', 2, 10))
        self.assertTrue(self.survives('Live Music', 2, 10, held={'Live Music'}))
        # A held tag the crawls stopped carrying still drops.
        self.assertFalse(self.survives('Live Music', 1, 10, held={'Live Music'}))
        self.assertFalse(self.survives('DJ', 0, 3, held={'DJ'}))
        self.assertEqual([tag_keep_threshold(n) for n in (2, 6, 7, 10, 14, 20)], [1, 1, 2, 2, 3, 3])

    def test_alternating_crawls_no_longer_flap_a_held_curated_tag(self):
        held, history = set(), []
        states = []
        for crawl in range(8):
            current = {'Virtual'} if crawl % 2 == 0 else set()
            history.append(current)
            count = sum('Virtual' in c for c in history)
            if self.survives('Virtual', count, len(history), current, held):
                held = {'Virtual'}
            else:
                held = set()
            states.append(bool(held))
        self.assertEqual(states, [True] * 8)


class Cursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def execute(self, query, params=()):
        return self.cursor.execute(query.replace('%s', '?'), params)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class MetadataSQLTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.cursor = Cursor(self.db)
        self.db.executescript('''
            CREATE TABLE events(id INT,website_id INT,reviewed INT,suppressed INT,
                location_id INT,location_name TEXT,sublocation TEXT,description TEXT);
            CREATE TABLE crawl_results(id INT,website_id INT,crawled_at TEXT);
            CREATE TABLE crawl_events(id INT,crawl_result_id INT,location_id INT,
                location_name TEXT,sublocation TEXT,description TEXT,raw_data TEXT,url TEXT);
            CREATE TABLE event_sources(event_id INT,crawl_event_id INT);
            CREATE TABLE event_occurrences(event_id INT,start_date TEXT,start_time TEXT,end_date TEXT);
            CREATE TABLE crawl_event_occurrences(crawl_event_id INT,start_date TEXT,start_time TEXT,end_date TEXT);
            INSERT INTO events VALUES(1,10,0,0,5,'School',NULL,'Old source text');
            INSERT INTO crawl_results VALUES(100,10,'2026-09-19 10:00:00'),(101,10,'2026-09-21 10:00:00');
            INSERT INTO crawl_events VALUES(20,100,5,'School',NULL,'Old source text','{}',NULL),
                (21,101,5,'School','Room 101','New RSVP information','{}',NULL);
            INSERT INTO event_sources VALUES(1,20);
            INSERT INTO event_occurrences VALUES(1,'2026-10-01','6pm',NULL);
            INSERT INTO crawl_event_occurrences VALUES(21,'2026-10-01','6pm',NULL);
        ''')

    def refresh(self, logger=None):
        return refresh_source_metadata(self.cursor, 1, 21, date(2026, 9, 21), logger)

    def test_sql_updates_and_audits_only_planned_fields_then_is_idempotent(self):
        logger = Mock()
        self.assertEqual(self.refresh(logger), dict(sublocation='Room 101', description='New RSVP information'))
        self.assertEqual(self.db.execute('SELECT description,sublocation,reviewed,location_id FROM events').fetchone(),
                         ('New RSVP information', 'Room 101', 0, 5))
        logger.log_update.assert_any_call('events', 1, 'description', 'Old source text', 'New RSVP information')
        logger.log_update.assert_any_call('events', 1, 'sublocation', None, 'Room 101')
        self.assertEqual(self.refresh(), {})

    def test_sql_preserves_reviewed_text_and_specific_room(self):
        self.db.execute("UPDATE events SET reviewed=1,sublocation='Auditorium'")
        self.assertEqual(self.refresh(), {})
        self.assertEqual(self.db.execute('SELECT description,sublocation FROM events').fetchone(),
                         ('Old source text', 'Auditorium'))

    def test_sql_price_only_refresh_preserves_text_and_audits_only_the_room(self):
        self.db.execute("UPDATE crawl_events SET description='Price: Free.' WHERE id=21")
        logger = Mock()
        self.assertEqual(self.refresh(logger), {'sublocation': 'Room 101'})
        self.assertEqual(self.db.execute('SELECT description FROM events').fetchone()[0], 'Old source text')
        logger.log_update.assert_called_once_with('events', 1, 'sublocation', None, 'Room 101')

    def test_sql_stub_refresh_keeps_detail_text_and_audits_only_the_room(self):
        detail = 'Detail-page program text. ' * 10
        self.db.execute('UPDATE events SET description=?', (detail,))
        self.db.execute('UPDATE crawl_events SET description=? WHERE id=20', (detail,))
        self.db.execute("UPDATE crawl_events SET description='Class at School. Price: $45.' WHERE id=21")
        logger = Mock()
        self.assertEqual(self.refresh(logger), {'sublocation': 'Room 101'})
        self.assertEqual(self.db.execute('SELECT description FROM events').fetchone()[0], detail)
        logger.log_update.assert_called_once_with('events', 1, 'sublocation', None, 'Room 101')

    def test_sql_reads_other_sources_before_mutating(self):
        self.db.executescript("INSERT INTO crawl_results VALUES(102,99,'2026-09-18 10:00:00');"
                             "INSERT INTO crawl_events VALUES(22,102,5,'School',NULL,'Other text','{}',NULL);"
                             'INSERT INTO event_sources VALUES(1,22);')
        self.assertEqual(self.refresh(), {})

    def test_sql_same_page_paraphrase_is_not_written_or_audited(self):
        self.db.execute("UPDATE crawl_events SET url='https://school.org/e/1'")
        self.db.execute("UPDATE events SET sublocation='Room 101'")
        self.db.execute("UPDATE crawl_events SET description='The old text from the source.' WHERE id=21")
        logger = Mock()
        self.assertEqual(self.refresh(logger), {})
        self.assertEqual(self.db.execute('SELECT description FROM events').fetchone()[0], 'Old source text')
        logger.log_update.assert_not_called()

    def test_sql_restores_delivery_label_even_without_room_or_text_change(self):
        self.db.execute("UPDATE crawl_events SET location_name='Online (Zoom)',sublocation=NULL,"
                        "description='Old source text' WHERE id=21")
        logger = Mock()
        self.assertEqual(self.refresh(logger), {'location_name': 'Online (Zoom)'})
        self.assertEqual(self.db.execute('SELECT location_id,location_name FROM events').fetchone(),
                         (5, 'Online (Zoom)'))
        logger.log_update.assert_called_once_with('events', 1, 'location_name', 'School', 'Online (Zoom)')
        self.assertEqual(self.refresh(), {})


if __name__ == '__main__':
    unittest.main()
