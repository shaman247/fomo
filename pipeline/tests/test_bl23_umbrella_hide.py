"""BL23 R1: season / program umbrellas covered by dated rows are hidden.

User ruling 2026-10-23 (decisions.md#season-umbrellas-hidden-2026-10-23): when a
team season or program series has individually dated rows, the untimed season /
series umbrella is hidden (suppressed=1, reviewed=1). `plan_umbrella_hide` is the
pure decision; `hide_covered_umbrellas` is the merge-tail step.

The pure tests need no database. The database tests run on connection-local
TEMPORARY tables (FOMO_TEST_TEMP_DB=1); no production rows are read or changed.
Run: cd pipeline/tests && PYTHONPATH=..:../.. FOMO_TEST_TEMP_DB=1 ../../venv/bin/python test_bl23_umbrella_hide.py
"""
import contextlib
import io
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merger

TODAY = date(2026, 10, 23)
HORIZON = TODAY + timedelta(days=90)


def d(month, day):
    return date(2026, month, day)


def span(start, end):
    return (start, '', end, '')


def day(dt, time=''):
    return (dt, time, None, '')


def umbrella(name, occs, description='', event_type='Screening', website_id=50, uid=1,
             location_names=('Film Forum',)):
    return {'id': uid, 'name': name, 'description': description, 'event_type': event_type,
            'website_id': website_id, 'location_id': 296, 'occurrences': list(occs),
            'location_names': list(location_names)}


def child(cid, name, occs, event_type='Screening', website_id=50, description='', urls=()):
    return {'id': cid, 'name': name, 'event_type': event_type, 'website_id': website_id,
            'description': description, 'section': 'Events', 'urls': list(urls),
            'occurrences': list(occs)}


def plan(u, children, past=(), **kw):
    return merger.plan_umbrella_hide(u, children, TODAY, HORIZON, past, **kw)


# William Greaves 100 (Film Forum, e284379): one untimed Oct 23-29 envelope, a
# description that names six films, and a dated row per film.
GREAVES = umbrella(
    'William Greaves 100', [span(d(10, 23), d(10, 29))],
    'Film series running Friday, October 23 - Thursday, October 29, with films including '
    'SYMBIOPSYCHOTAXIPLASM: TAKE ONE, NATIONTIME, LOST BOUNDARIES and RALPH BUNCHE: AN '
    'AMERICAN ODYSSEY.')
GREAVES_FILMS = [
    child(11, 'Symbiopsychotaxiplasm: Take One - Introduced by Producer Liani Greaves',
          [day(d(10, 23), '7pm')]),
    child(12, 'Nationtime', [day(d(10, 23), '2pm'), day(d(10, 26), '4pm')]),
    child(13, 'Lost Boundaries', [day(d(10, 24), '1pm')]),
    child(14, 'Ralph Bunche', [day(d(10, 28), '6pm')]),
]

# Kou Records at Blank Forms (e284908): a declared fall season, Oct 16 - Dec 5,
# whose three dated programs sit mid-season (Nov 10, 12, 14).
KOU = umbrella('Kou Records at Blank Forms—Fall 2026 season',
               [span(d(10, 16), d(12, 5))],
               'Kou Records at Blank Forms fall 2026 season, running October 16-December 5, 2026.',
               event_type='Concert', website_id=638, location_names=('Blank Forms',))
KOU_PROGRAMS = [child(21, 'Drew McDowall: Coil', [day(d(11, 10), '7:30pm')], 'Concert', 638,
                      'Part of the Kou Records season at Blank Forms.'),
                child(22, 'Oren Ambarchi trio', [day(d(11, 12), '7:30pm')], 'Concert', 638,
                      urls=['https://www.blankforms.org/events/kou-records-oren-ambarchi']),
                child(23, 'Kou Records: Laetitia Sonami', [day(d(11, 14), '7:30pm')],
                      'Concert', 638)]
# The live e284908 "children" (2026-10-23 replay): Keiji Haino's own Blank Forms
# residency, which the season's own description never names.
HAINO_RESIDENCY = [
    child(21, 'Keiji Haino solo & duo with Loren Connors', [day(d(11, 10), '7:30pm')],
          'Concert', 638, 'Keiji Haino performs as part of his Blank Forms residency.',
          ['https://www.blankforms.org/events/keiji-haino-solo-duo-with-loren-connors']),
    child(22, 'Keiji Haino & special guest', [day(d(11, 12), '7:30pm')], 'Concert', 638,
          urls=['https://www.blankforms.org/events/keiji-haino-special-guest']),
    child(23, 'Fushitsusha', [day(d(11, 14), '7:30pm')], 'Concert', 638,
          urls=['https://www.blankforms.org/events/fushitsusha'])]

# Rossellini 120 (Film Forum, e302792, hidden by the rc1023d merge and restored
# by hand): a declared series naming no titles, "covered" by the venue's
# unrelated Lubitsch / McCarey / FF Jr. screenings whose dates happened to reach
# both ends of its window (Nov 23 and Dec 7 against Nov 20 - Dec 10).
ROSSELLINI = umbrella(
    'Rossellini 120', [span(d(11, 20), d(12, 10))],
    'A Roberto Rossellini series running Friday, November 20 – Thursday, December 10.',
    uid=302792)
FILM_FORUM_OTHERS = [
    child(302801, "Lady Windermere's Fan", [day(d(11, 23), '6:30pm')],
          description='No description available.',
          urls=['https://my.filmforum.org/lady-windermeres-fan/53572']),
    child(302802, 'Pinocchio', [day(d(11, 29), '11am')], description='No description available.',
          urls=['https://my.filmforum.org/pinocchio-ffjr/52519']),
    child(302803, 'The Marriage Circle', [day(d(11, 30), '6pm')],
          description='No description available.',
          urls=['https://my.filmforum.org/the-marriage-circle/53574']),
    child(302804, "The Bells of ST. Mary's", [day(d(12, 6), '11am')],
          description='No description available.',
          urls=['https://my.filmforum.org/the-bells-of-st-marys-ffjr/52521']),
    child(302805, "I Don't Want to Be a Man", [day(d(12, 7), '6:10pm')],
          description='No description available.',
          urls=['https://my.filmforum.org/i-dont-want-to-be-a-man/53576']),
]


class PlanUmbrellaHideTests(unittest.TestCase):
    def test_film_series_with_a_row_per_named_film_is_hidden(self):
        self.assertEqual(plan(GREAVES, GREAVES_FILMS), ('hide', [11, 12, 13, 14]))

    def test_kou_season_with_mid_season_programs_is_hidden(self):
        self.assertEqual(plan(KOU, KOU_PROGRAMS), ('hide', [21, 22, 23]))

    def test_kou_season_over_another_residency_keeps(self):
        # The live shape: the dated rows are Keiji Haino's residency, not Kou's.
        self.assertEqual(plan(KOU, HAINO_RESIDENCY),
                         ('keep', 'no series identity "kou records" in e21, e22, e23'))

    def test_rossellini_series_over_unrelated_films_keeps(self):
        # BL23 R1 false positive 2026-10-23 (e302792).
        self.assertEqual(plan(ROSSELLINI, FILM_FORUM_OTHERS),
                         ('keep', 'no series identity "rossellini" in e302801, e302802, '
                                  'e302803, e302804, e302805'))

    def test_rossellini_series_with_its_own_films_is_hidden(self):
        films = [child(91, 'Rome Open City', [day(d(11, 20), '7pm')],
                       urls=['https://filmforum.org/series/rossellini/rome-open-city']),
                 child(92, 'Stromboli', [day(d(11, 27), '7pm')],
                       description='Part of our Rossellini 120 retrospective.'),
                 child(93, 'Rossellini: Journey to Italy', [day(d(12, 9), '7pm')])]
        self.assertEqual(plan(ROSSELLINI, films + FILM_FORUM_OTHERS), ('hide', [91, 92, 93]))

    def test_identity_rows_alone_must_still_cover(self):
        # One identity row plus unrelated films that reach the edges: keep.
        films = [child(91, 'Rome Open City', [day(d(11, 27), '7pm')],
                       urls=['https://filmforum.org/series/rossellini/rome-open-city'])]
        action, detail = plan(ROSSELLINI, films + FILM_FORUM_OTHERS)
        self.assertEqual(action, 'keep')
        self.assertNotIn('e91', detail)

    def test_umbrella_identity(self):
        cases = {
            'Rossellini 120': ('phrase', 'rossellini'),
            'Kou Records at Blank Forms—Fall 2026 season': ('phrase', 'kou records'),
            'Area Coded: American Regionalism in Film': ('phrase', 'area coded'),
            'New York City Center Fall Season': ('venue', None),
            'New York Knicks Basketball': ('phrase', 'knicks'),
            'Fall Film Series': ('none', None),
        }
        names = ['Blank Forms', 'New York City Center', 'Film Forum']
        for name, expected in cases.items():
            self.assertEqual(merger._umbrella_identity({'name': name, 'location_names': names}),
                             expected, name)

    def test_kou_season_with_two_programs_and_no_edge_coverage_stays(self):
        action, _ = plan(KOU, KOU_PROGRAMS[:2])
        self.assertIsNone(action)

    def test_aggregator_season_card_is_covered_by_any_format_from_any_site(self):
        # NYC Tourism "New York City Center Fall Season" (e235376, typed Festival).
        # A venue season: sharing the venue is the identity.
        card = umbrella('New York City Center Fall Season', [span(d(9, 22), d(11, 15))],
                        event_type='Festival', website_id=3524,
                        location_names=('New York City Center',))
        runs = [child(31, 'The Unbelievers', [day(d(10, 23), '7pm'), day(d(11, 14), '7pm')],
                      'Theater Show', 235),
                child(32, 'In the Heights Benefit', [day(d(11, 4), '7pm')], 'Theater Show', 367)]
        self.assertEqual(plan(card, runs, aggregator=True), ('hide', [31, 32]))
        # The same card from a venue's own website needs its own format.
        self.assertIsNone(plan(card, runs)[0])

    def test_named_title_without_a_row_keeps_and_reports_it(self):
        action, detail = plan(GREAVES, [c for c in GREAVES_FILMS if c['id'] != 13])
        self.assertEqual(action, 'keep')
        self.assertIn('LOST BOUNDARIES', detail)

    def test_named_title_that_already_screened_counts(self):
        films = [c for c in GREAVES_FILMS if c['id'] != 13]
        self.assertEqual(plan(GREAVES, films, past=['Lost Boundaries'])[0], 'hide')

    def test_exhibition_with_an_opening_reception_stays(self):
        show = umbrella('Fall Series: New Paintings', [span(d(10, 1), d(12, 20))],
                        'An exhibition series.', event_type='Exhibition')
        receptions = [child(41, 'Opening Reception', [day(d(10, 24), '6pm')], 'Exhibition'),
                      child(42, 'Closing Reception', [day(d(12, 19), '6pm')], 'Exhibition')]
        self.assertIsNone(plan(show, receptions)[0])

    def test_recurring_series_with_one_special_edition_stays(self):
        series = umbrella('Sunday Jazz Series', [span(d(10, 4), d(12, 27))],
                          event_type='Concert', website_id=7)
        special = [child(51, 'Sunday Jazz Series: Holiday Special', [day(d(12, 20), '2pm')],
                         'Concert', 7)]
        self.assertIsNone(plan(series, special)[0])

    def test_festival_umbrella_always_stays(self):
        # User ruling 2026-10-23: festival umbrellas stay visible (hard exclusion).
        fest = umbrella('Baltic Film Festival Series', [span(d(10, 23), d(10, 29))])
        self.assertEqual(plan(fest, GREAVES_FILMS), (None, 'festival (always kept visible)'))
        newfest = umbrella('NewFest Series', [span(d(10, 23), d(10, 29))])
        self.assertIsNone(plan(newfest, GREAVES_FILMS)[0])

    def test_hybrid_series_row_with_its_own_days_stays(self):
        # IFC "Optic Nerve": the span plus one untimed date per screening day.
        optic = umbrella('Optic Nerve: A Tribute to Glass Eye Pix',
                         [span(d(10, 28), d(11, 3))] + [day(d(10, 28) + timedelta(i))
                                                        for i in range(7)],
                         'A series celebrating 40 years of Glass Eye Pix, Oct 28 - Nov 3.')
        films = [child(61, 'Closure', [day(d(10, 28), '6:45pm'), day(d(10, 29), '6:45pm')]),
                 child(62, 'Gentle Monster', [day(d(10, 30))]),
                 child(63, 'Op-Docs', [day(d(11, 2), '6:30pm')])]
        self.assertEqual(plan(optic, films), (None, 'carries its own dated days'))

    def test_timed_umbrella_stays(self):
        timed = umbrella('Staff Picks Series', [span(d(10, 23), d(10, 29)), day(d(10, 24), '9pm')])
        self.assertEqual(plan(timed, GREAVES_FILMS), (None, 'timed occurrence'))

    def test_undeclared_run_stays(self):
        # A comedy residency, a month-long library activity: a span, no series/season.
        run = umbrella('Drew Michael: Love Me', [span(d(10, 23), d(11, 20))],
                       'An immersive experience felt from the inside.', event_type='Comedy Show')
        shows = [child(71, 'Bigfoot', [day(d(10, 24), '7pm')], 'Comedy Show'),
                 child(72, 'Kevin!!!!!', [day(d(11, 19), '7pm')], 'Comedy Show'),
                 child(73, 'Fly, You Fools!', [day(d(11, 1), '7pm')], 'Comedy Show')]
        self.assertEqual(plan(run, shows)[0], None)

    def test_spooky_season_and_seasons_greetings_do_not_declare(self):
        for name in ("Spooky Season!: Halloween Activity Station",
                     "Short Attention Span Cinema: Season's Greetings"):
            u = umbrella(name, [span(d(10, 23), d(10, 31))], f'{name}.')
            self.assertIsNone(plan(u, GREAVES_FILMS)[0], name)

    def test_series_declared_only_in_description_needs_a_week_long_span(self):
        short = umbrella('Area Coded', [span(d(10, 23), d(10, 27))],
                         'The films in this series explore American places.')
        self.assertIsNone(plan(short, GREAVES_FILMS)[0])
        week = umbrella('Area Coded', [span(d(10, 23), d(10, 29))],
                        'The films in this series explore American places.')
        # Names no titles, so the venue's other films do not cover it ...
        self.assertEqual(plan(week, GREAVES_FILMS)[0], 'keep')
        # ... but its own films (BAM slugs /film/2026/area-coded-<title>) do,
        # and a new release on the same dates is left out of the cover.
        films = [child(c['id'], c['name'], c['occurrences'],
                       urls=[f"https://www.bam.org/film/2026/area-coded-{c['id']}"])
                 for c in GREAVES_FILMS]
        other = child(19, 'Wild Horse Nine', [day(d(10, 24), '7pm')],
                      urls=['https://www.bam.org/film/2026/wild-horse-nine'])
        self.assertEqual(plan(week, films + [other]), ('hide', [11, 12, 13, 14]))

    def test_team_season_name_declares(self):
        card = umbrella('New York Knicks Basketball', [span(d(10, 20), date(2027, 4, 11))],
                        event_type='Sports', website_id=3524)
        games = [child(81, 'Knicks vs. Celtics', [day(d(10, 24), '7:30pm')], 'Sports', 271),
                 child(82, 'Knicks vs. Heat', [day(date(2027, 1, 19), '7:30pm')], 'Sports', 271)]
        self.assertEqual(plan(card, games, aggregator=True), ('hide', [81, 82]))

    def test_other_formats_at_the_venue_do_not_cover_a_series(self):
        talks = [child(c['id'], c['name'], c['occurrences'], 'Talk') for c in GREAVES_FILMS]
        self.assertIsNone(plan(GREAVES, talks)[0])

    def test_past_umbrella_is_ignored(self):
        old = umbrella('Andrzej Wajda 100 series', [span(d(10, 2), d(10, 22))])
        self.assertEqual(plan(old, GREAVES_FILMS), (None, 'past'))

    def test_listed_titles_parse(self):
        titles = [t for t, _ in merger._umbrella_listed_titles(
            "Third annual series, including Agnès Jaoui's The Taste of Others, Guy "
            "Gilles's The Garden That Tilts, and Claude Chabrol's Les Godelureaux. More.")]
        self.assertEqual(titles, ["Agnès Jaoui's The Taste of Others",
                                  "Guy Gilles's The Garden That Tilts",
                                  "Claude Chabrol's Les Godelureaux"])
        self.assertEqual(merger._umbrella_listed_titles('featuring A, B and more'),
                         [('A', 'a'), ('B', 'b')])


class _Logger:
    def __init__(self):
        self.updates = []

    def log_update(self, table, row_id, field, old, new):
        self.updates.append((table, row_id, field, old, new))


@unittest.skipUnless(os.environ.get('FOMO_TEST_TEMP_DB') == '1',
                     'Opt in to connection-local MariaDB tests with FOMO_TEST_TEMP_DB=1')
class HideCoveredUmbrellasDbTests(unittest.TestCase):
    SCHEMAS = {
        'events': ('id INT PRIMARY KEY, name VARCHAR(255), description TEXT, '
                   'section VARCHAR(50), event_type VARCHAR(50), website_id INT, location_id INT, '
                   'archived TINYINT DEFAULT 0, suppressed TINYINT DEFAULT 0, '
                   'reviewed TINYINT DEFAULT 0'),
        'event_occurrences': ('id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, start_date DATE, '
                              'start_time VARCHAR(20), end_date DATE NULL, end_time VARCHAR(20)'),
        'websites': 'id INT PRIMARY KEY, source_type VARCHAR(20)',
        'locations': ('id INT PRIMARY KEY, name VARCHAR(255), short_name VARCHAR(255), '
                      'very_short_name VARCHAR(255)'),
        'event_urls': 'id INT AUTO_INCREMENT PRIMARY KEY, event_id INT, url VARCHAR(1000)',
    }

    def setUp(self):
        from db import create_connection
        self.conn = create_connection()
        self.assertIsNotNone(self.conn)
        self.addCleanup(self.conn.close)
        self.cur = self.conn.cursor()
        for table, schema in self.SCHEMAS.items():
            self.cur.execute(f'CREATE TEMPORARY TABLE {table} ({schema})')
        self.cur.execute("INSERT INTO websites VALUES (50, 'venue'), (638, 'venue'), "
                         "(3524, 'aggregator')")
        # Connection-local TEMPORARY table (see SCHEMAS); no real location row.
        self.cur.execute("INSERT INTO locations VALUES (296, 'Film Forum', NULL, NULL), "
                         "(2026, 'Blank Forms', NULL, NULL), "
                         "(602, 'New York City Center', 'City Center', NULL)")
        settings = patch('merger._umbrella_aggregator_settings', return_value=set())
        settings.start()
        self.addCleanup(settings.stop)

    def add(self, row, location_id=296, **state):
        cols = dict(id=row['id'], name=row['name'], description=row.get('description', ''),
                    event_type=row['event_type'], website_id=row['website_id'],
                    location_id=location_id, **state)
        self.cur.execute(f"INSERT INTO events ({','.join(cols)}) VALUES "
                         f"({','.join(['%s'] * len(cols))})", list(cols.values()))
        for occ in row['occurrences']:
            self.cur.execute('INSERT INTO event_occurrences (event_id,start_date,start_time,'
                             'end_date,end_time) VALUES (%s,%s,%s,%s,%s)', (row['id'], *occ))
        for url in row.get('urls', ()):
            self.cur.execute('INSERT INTO event_urls (event_id, url) VALUES (%s, %s)',
                             (row['id'], url))

    def run_step(self, website_ids, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            decisions = merger.hide_covered_umbrellas(
                self.cur, self.conn, website_ids, today=TODAY, horizon=HORIZON, **kw)
        return decisions, out.getvalue()

    def state(self, event_id):
        self.cur.execute('SELECT suppressed, reviewed FROM events WHERE id = %s', (event_id,))
        return self.cur.fetchone()

    def test_hides_and_logs_a_covered_series(self):
        self.add(GREAVES)
        for film in GREAVES_FILMS:
            self.add(film)
        logger = _Logger()
        decisions, out = self.run_step([50], edit_logger=logger)
        self.assertEqual(decisions, [(1, 'hide', [11, 12, 13, 14])])
        self.assertIn('UMBRELLA-HIDDEN e1 "William Greaves 100" covered by e11, e12, e13, e14', out)
        self.assertEqual(self.state(1), (1, 1))
        self.assertEqual(self.state(11), (0, 0))
        self.assertEqual(logger.updates, [('events', 1, 'suppressed', 0, 1),
                                          ('events', 1, 'reviewed', 0, 1)])

    def test_dry_run_writes_nothing(self):
        self.add(KOU, location_id=2026)
        for program in KOU_PROGRAMS:
            self.add(program, location_id=2026)
        decisions, out = self.run_step([638], apply=False)
        self.assertEqual([d[1] for d in decisions], ['hide'])
        self.assertIn('UMBRELLA-HIDDEN e1', out)
        self.assertEqual(self.state(1), (0, 0))

    def test_reviewed_visible_keep_is_never_touched(self):
        self.add(GREAVES, reviewed=1)
        for film in GREAVES_FILMS:
            self.add(film)
        decisions, _ = self.run_step([50])
        self.assertEqual(decisions, [])
        self.assertEqual(self.state(1), (0, 1))

    def test_out_of_scope_website_is_skipped(self):
        self.add(GREAVES)
        for film in GREAVES_FILMS:
            self.add(film)
        self.assertEqual(self.run_step([12])[0], [])

    def test_aggregator_card_is_judged_from_any_merge_scope(self):
        card = umbrella('New York City Center Fall Season', [span(d(9, 22), d(11, 15))],
                        event_type='Festival', website_id=3524)
        self.add(card, location_id=602)
        self.add(child(31, 'The Unbelievers', [day(d(10, 23), '7pm'), day(d(11, 14), '7pm')],
                       'Theater Show', 235), location_id=602)
        self.add(child(32, 'In the Heights', [day(d(11, 4), '7pm')], 'Theater Show', 367),
                 location_id=602)
        decisions, _ = self.run_step([235])
        self.assertEqual(decisions, [(1, 'hide', [31, 32])])

    def test_rossellini_shape_keeps_and_logs(self):
        # BL23 R1 false positive 2026-10-23: kept, logged, untouched.
        self.add(ROSSELLINI)
        for film in FILM_FORUM_OTHERS:
            self.add(film)
        decisions, out = self.run_step([50])
        self.assertEqual([d[:2] for d in decisions], [(302792, 'keep')])
        self.assertIn('UMBRELLA-KEEP-UNCOVERED e302792 no series identity "rossellini" in '
                      'e302801, e302802, e302803, e302804, e302805', out)
        self.assertEqual(self.state(302792), (0, 0))

    def test_series_identity_read_from_urls_and_descriptions(self):
        self.add(ROSSELLINI)
        for film in FILM_FORUM_OTHERS:
            self.add(film)
        self.add(child(91, 'Rome Open City', [day(d(11, 21), '7pm')],
                       urls=['https://filmforum.org/series/rossellini/rome-open-city']))
        self.add(child(92, 'Journey to Italy', [day(d(12, 8), '7pm')],
                       description='A Rossellini 120 screening.'))
        decisions, out = self.run_step([50])
        self.assertEqual(decisions, [(302792, 'hide', [91, 92])])
        self.assertEqual(self.state(302792), (1, 1))

    def test_archived_and_suppressed_rows_do_not_cover(self):
        self.add(GREAVES)
        for film in GREAVES_FILMS[:2]:
            self.add(film)
        for film in GREAVES_FILMS[2:]:
            self.add(film, archived=1)
        decisions, out = self.run_step([50])
        # Two visible rows reach both ends; the archived rows still satisfy the
        # named-title check as already-screened titles.
        self.assertEqual(decisions, [(1, 'hide', [11, 12])])
        self.cur.execute('UPDATE events SET suppressed = 0, reviewed = 0 WHERE id = 1')
        self.cur.execute('UPDATE events SET suppressed = 1 WHERE id IN (13, 14)')
        decisions, out = self.run_step([50])
        self.assertEqual(decisions, [(1, 'keep', 'missing LOST BOUNDARIES')])
        self.assertIn('UMBRELLA-KEEP-UNCOVERED e1 missing LOST BOUNDARIES', out)
        self.assertEqual(self.state(1), (0, 0))


if __name__ == '__main__':
    unittest.main()
